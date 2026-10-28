"""CapitalBeep: a short tone whenever a capital letter is read as a character.

Intended to be used alongside Orca's "pitch change" capitalization style, which
handles whole capitalised lines nicely but is inaudible on some letters with some
voices. This add-on covers the gap without the chatter of "icon" or the loss of
the capitals-pitch line reading that "spell" causes.

The rule: a unit of exactly one uppercase letter, read as a unit, beeps. That is

  * character navigation, in caret navigation and in flat review,
  * spelling, including phonetic spelling,
  * character and key echo while typing, and echo when deleting,
  * a word that is a single letter (I, A).

Reading a whole word or line never beeps, however it is capitalised: "is" and
"IS" are both silent, because neither is read one character at a time.

Toggle with Orca+Ctrl+Shift+C.
"""

from __future__ import annotations

import json
import logging
import os

from gi.repository import GLib

from orca import presentation_manager, speech_manager, speech_presenter

from .tone import BeepPlayer, render_wav

_log = logging.getLogger("orca-capitalbeep")

# --- Tunables ---------------------------------------------------------------

# 660 Hz is E5 (E5 is 659.25 Hz); A5 would be 880.
FREQUENCY_HZ = 660
DURATION_MS = 80
FADE_MS = 8

# Orca's speech volume is 0.0-10.0; GStreamer's is 0.0-1.0. A full-scale sine is
# far louder than speech at the same nominal setting, so scale it down. Raise or
# lower this one number to balance the beep against your voice.
VOLUME_HEADROOM = 0.35

# --- State ------------------------------------------------------------------

_DATA_DIR = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "orca",
    "capitalbeep",
)
_STATE_PATH = os.path.join(_DATA_DIR, "state.json")

_enabled = True
_player: BeepPlayer | None = None

# Every monkey-patch we apply, as (owner, attribute, original, was_own).
# Recorded so uninstall() can put things back exactly as they were. This
# matters for more than tidiness: the extension loader re-imports the
# module on reload, so a fresh module -- with its _orig_* guards all back
# to None -- would otherwise wrap the already wrapped methods and every
# capital would beep twice.
_patched_targets: list = []


def _patch(owner, attr, replacement) -> None:
    """Install replacement on owner.attr, remembering what was there."""
    try:
        was_own = attr in vars(owner)
    except TypeError:
        was_own = True
    _patched_targets.append((owner, attr, getattr(owner, attr), was_own))
    setattr(owner, attr, replacement)


def _unpatch_all() -> None:
    """Restore every patched attribute, most recent first."""
    while _patched_targets:
        owner, attr, original, was_own = _patched_targets.pop()
        try:
            if was_own:
                setattr(owner, attr, original)
            else:
                # It was inherited from the class; deleting the instance
                # attribute we added restores the original lookup rather
                # than pinning a bound method onto the instance.
                delattr(owner, attr)
        except Exception as error:  # pylint: disable=broad-exception-caught
            _log.warning("CapitalBeep: could not restore %s: %s", attr, error)

# Reading a character is always beepable, so it needs no gate. Reading a *word*
# is beepable only when the word turns out to be a single letter, and that is
# decided from the spoken text, so those paths arm a gate for their duration.
# Depth is a counter because the web script's say_word() delegates to the default
# script's for non-document content, which re-enters the wrapper.
_word_depth = 0
_word_beeped = False

_installed = False


def _load_state() -> None:
    global _enabled
    try:
        with open(_STATE_PATH, "r", encoding="utf-8") as handle:
            _enabled = bool(json.load(handle).get("enabled", True))
    except FileNotFoundError:
        _enabled = True
    except Exception as error:
        _log.warning("CapitalBeep: could not read state: %s", error)
        _enabled = True


def _save_state() -> None:
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as handle:
            json.dump({"enabled": _enabled}, handle)
    except Exception as error:
        _log.warning("CapitalBeep: could not write state: %s", error)


# --- The beep ---------------------------------------------------------------


def _beep_volume() -> float:
    """Track Orca's speech volume, scaled into GStreamer's range."""
    try:
        volume = speech_manager.get_manager().get_volume()
    except Exception:
        volume = 10.0
    return max(0.0, min(1.0, (volume / 10.0) * VOLUME_HEADROOM))


def _is_capital(text: str) -> bool:
    """True if text is exactly one uppercase letter, matching Orca's own test."""
    stripped = text.strip()
    return len(stripped) == 1 and stripped.isupper() and stripped.isalpha()


def _beep() -> None:
    """Play the tone, unless the add-on or speech itself is off."""
    if not _enabled or _player is None:
        return
    try:
        if speech_manager.get_manager().get_speech_is_muted():
            return
    except Exception:
        pass
    _player.play(_beep_volume())


def _beep_for_character(text: str) -> None:
    """Beep for a character being read on its own. Always allowed, never gated."""
    if _is_capital(text):
        _beep()


def _beep_for_word(text: str) -> None:
    """Beep for a word unit, but only if the whole word is one letter.

    Gated, because the same speech call also carries lines and multi-word text,
    which must stay silent however they are capitalised.
    """
    global _word_beeped

    if _word_depth == 0 or _word_beeped:
        return
    if not _is_capital(text):
        return
    _word_beeped = True
    _beep()


def _flatten(content) -> str:
    """Collect the plain strings out of a speech generator utterance list."""
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        return " ".join(
            _flatten(item) for item in content if isinstance(item, (str, list, tuple))
        )
    return ""


# --- Hooks ------------------------------------------------------------------

_orig_speak = None
_orig_speak_character = None
_orig_spell_item = None
_orig_spell_phonetically = None
_orig_sd_char = None
_orig_sd_speak = None

# Speech Dispatcher lets us hang a callback on an individual queued message, so a
# beep can be fired at the instant its letter starts being spoken instead of the
# instant it is queued. That only matters when spelling, where Orca queues every
# character up front and the Python loop finishes in about a millisecond. See
# _spell_item_hook for the full reasoning.
_sync_available = False
_sync_depth = 0
_pending_sync_beep = False


def _speak_hook(text, voice_type=None):
    """Word-level speech: only a single-letter word beeps, and only when gated.

    Orca 51 changed the signature of the public speak entry point:
    old speech.speak(content, acss=None) → new speech_presenter.speak_message(
    text, voice_type=SYSTEM). We hook the new signature and forward voice_type
    when it was explicitly passed."""
    try:
        _beep_for_word(_flatten(text))
    except Exception as error:
        _log.error("CapitalBeep: beep failed in speak: %s", error)
    if voice_type is None:
        return _orig_speak(text)
    return _orig_speak(text, voice_type)


def _speak_character_hook(character, voice_from="", cap_style=None,
                          obj=None, language="", dialect=""):
    """Every character Orca reads on its own passes through here.

    That covers character navigation, flat review, spell_item()'s per-character
    loop, key echo, character echo while typing, and echo when deleting.
    """
    global _pending_sync_beep
    try:
        if _is_capital(character):
            if _sync_depth > 0:
                # Let the Speech Dispatcher hook fire this one when the letter
                # actually starts, rather than now.
                _pending_sync_beep = True
            else:
                _beep()
    except Exception as error:
        _log.error("CapitalBeep: beep failed in speak_character: %s", error)
    return _orig_speak_character(character, voice_from=voice_from,
                                 cap_style=cap_style, obj=obj,
                                 language=language, dialect=dialect)


# --- Synchronising a beep to the letter it belongs to ------------------------


def _beep_on_main_loop() -> bool:
    _beep()
    return False


def _on_message_begin(_callback_type, **_kwargs) -> None:
    """Runs in Speech Dispatcher's listener thread, so do nothing here but defer.

    speechd's own documentation is explicit that a callback must not issue further
    SSIP commands, and GStreamer wants the main loop anyway.
    """
    GLib.idle_add(_beep_on_main_loop)


def _attach_begin_callback(client, result) -> bool:
    """Ask Speech Dispatcher to tell us when this queued message starts speaking."""
    try:
        import speechd

        msg_id = int(result[2][0])
        client._callback_handler.add_callback(
            msg_id,
            _on_message_begin,
            (speechd.CallbackType.BEGIN,),
        )
        return True
    except Exception as error:
        _log.error("CapitalBeep: could not attach begin callback: %s", error)
        return False


def _sd_char_hook(self, character):
    """speechd's own char() discards the reply, and with it the message id.

    The body here is that of speechd.SSIPClient.char, kept in step with it, run
    only when a beep is waiting to be synchronised; every other character goes
    straight to the original.
    """
    global _pending_sync_beep

    if not _pending_sync_beep:
        return _orig_sd_char(self, character)

    _pending_sync_beep = False
    result = self._conn.send_command("CHAR", character.replace(" ", "space"))
    if not _attach_begin_callback(self, result):
        GLib.idle_add(_beep_on_main_loop)
    return result


def _sd_speak_hook(self, text, callback=None, event_types=None):
    """speak() already takes a callback, so phonetic spelling needs no surgery."""
    global _pending_sync_beep

    if not _pending_sync_beep or callback is not None:
        # callback is not None means say-all, which owns its own notifications.
        _pending_sync_beep = False
        return _orig_sd_speak(self, text, callback, event_types)

    _pending_sync_beep = False
    try:
        import speechd

        return _orig_sd_speak(
            self, text, _on_message_begin, (speechd.CallbackType.BEGIN,)
        )
    except Exception as error:
        _log.error("CapitalBeep: could not sync beep to speech: %s", error)
        GLib.idle_add(_beep_on_main_loop)
        return _orig_sd_speak(self, text, callback, event_types)


def _spell_item_hook(self, text, *args, **kwargs):
    """Spelling a multi-letter string needs its beeps synchronised.

    Orca sends every character to Speech Dispatcher without waiting, so the loop
    is over in about a millisecond while the letters are still queued. Beeping as
    each character is queued would put all the beeps in a burst up front. Instead
    each capital arms _pending_sync_beep, and the char() hook turns that into a
    BEGIN callback on that one queued message.

    The original loops over the string calling speak_character, so driving it one
    character at a time is equivalent and lets a character that never reached
    Speech Dispatcher (a different speech backend, say) fall back to beeping now.

    *args/**kwargs: Orca grew spell_item's signature over time (obj, start_offset
    etc.). Accept whatever upstream calls us with, forward it on the fallback
    path, and drop it on the per-character path (where obj/offset mean the whole
    thing, not any individual character — the original ignored those for the
    per-character call too).
    """
    global _sync_depth, _pending_sync_beep

    if not _sync_available or len(text.strip()) <= 1:
        return _orig_spell_item(self, text, *args, **kwargs)

    for character in text:
        _sync_depth += 1
        try:
            _orig_spell_item(self, character)
        finally:
            _sync_depth -= 1
        if _pending_sync_beep:
            _pending_sync_beep = False
            _beep()
    return None


def _spell_phonetically_hook(self, item_string, *args, **kwargs):
    """Phonetic spelling needs an explicit beep: the case is gone by then.

    get_phonetic_name() lowercases its input, so "alpha" is spoken for both a and
    A and there is nothing in the spoken text left to detect. As with spell_item,
    the original loops over characters, so driving it one character at a time is
    equivalent and keeps each beep with its own letter.

    *args/**kwargs: upstream Orca's spell_phonetically grew extra positional
    params (obj, start_offset). Accept whatever we are called with and ignore it
    here — the per-character delegation does not forward them, matching the
    original's own behaviour inside its character loop.
    """
    global _pending_sync_beep

    try:
        sync = _sync_available and len(item_string.strip()) > 1
        for character in item_string:
            if _is_capital(character):
                if sync:
                    _pending_sync_beep = True
                else:
                    _beep()
            _orig_spell_phonetically(self, character)
            if _pending_sync_beep:
                _pending_sync_beep = False
                _beep()
        return None
    except Exception as error:
        _log.error("CapitalBeep: phonetic spelling hook failed: %s", error)
        return _orig_spell_phonetically(self, item_string)


def _wrap_word_reader(cls, method_name: str) -> bool:
    """Arm the word gate for the duration of a method that reads one word.

    Only wraps a method the class defines itself, so that a subclass delegating
    to super() does not get counted twice.
    """
    original = cls.__dict__.get(method_name)
    if original is None or getattr(original, "_capitalbeep_wrapped", False):
        return False

    def wrapper(self, *args, **kwargs):
        global _word_depth, _word_beeped
        if _word_depth == 0:
            _word_beeped = False
        _word_depth += 1
        try:
            return original(self, *args, **kwargs)
        finally:
            _word_depth -= 1

    wrapper._capitalbeep_wrapped = True
    wrapper.__name__ = method_name
    wrapper.__doc__ = original.__doc__
    _patch(cls, method_name, wrapper)
    return True


def _install_speech_dispatcher_hooks() -> None:
    """Optional: without these, spelling still beeps, just less precisely."""
    global _orig_sd_char, _orig_sd_speak, _sync_available

    try:
        import speechd
    except Exception as error:
        _log.warning("CapitalBeep: speechd unavailable, spelling beeps unsynced: %s", error)
        return

    try:
        if _orig_sd_char is None:
            _orig_sd_char = speechd.SSIPClient.char
            _patch(speechd.SSIPClient, "char", _sd_char_hook)
        if _orig_sd_speak is None:
            _orig_sd_speak = speechd.SSIPClient.speak
            _patch(speechd.SSIPClient, "speak", _sd_speak_hook)
        _sync_available = True
        _log.info("CapitalBeep: spelling beeps synchronised via Speech Dispatcher")
    except Exception as error:
        _log.error("CapitalBeep: could not hook Speech Dispatcher: %s", error)


def _install_hooks() -> None:
    global _orig_speak, _orig_speak_character
    global _orig_spell_item, _orig_spell_phonetically

    # Orca 51: monkey-patch the SpeechPresenter singleton's methods instead
    # of the old module-level speech.speak / speech.speak_character functions.
    _presenter = speech_presenter.get_presenter()
    if _orig_speak is None:
        _orig_speak = _presenter.speak_message
        _patch(_presenter, "speak_message", _speak_hook)
    if _orig_speak_character is None:
        _orig_speak_character = _presenter.speak_character
        _patch(_presenter, "speak_character", _speak_character_hook)

    if _orig_spell_item is None:
        _orig_spell_item = speech_presenter.SpeechPresenter.spell_item
        _patch(speech_presenter.SpeechPresenter, "spell_item", _spell_item_hook)
        _log.info("CapitalBeep: wrapped SpeechPresenter.spell_item")
    if _orig_spell_phonetically is None:
        _orig_spell_phonetically = speech_presenter.SpeechPresenter.spell_phonetically
        _patch(speech_presenter.SpeechPresenter, "spell_phonetically", _spell_phonetically_hook)
        _log.info("CapitalBeep: wrapped SpeechPresenter.spell_phonetically")

    _install_speech_dispatcher_hooks()

    # Word readers, so that a one-letter word beeps but a longer word does not.
    from orca.scripts import default as default_script

    targets = [(default_script.Script, "say_word")]
    try:
        from orca.scripts.web import script as web_script

        targets.append((web_script.Script, "say_word"))
    except Exception as error:
        _log.warning("CapitalBeep: web script unavailable, skipping: %s", error)

    try:
        from orca import flat_review_presenter

        targets.append((flat_review_presenter.FlatReviewPresenter, "_item_presentation"))
    except Exception as error:
        _log.warning("CapitalBeep: flat review unavailable, skipping: %s", error)

    for cls, method_name in targets:
        if _wrap_word_reader(cls, method_name):
            _log.info("CapitalBeep: wrapped %s.%s", cls.__name__, method_name)


# --- Toggle -----------------------------------------------------------------


def toggle() -> bool:
    """Command handler for Orca+Ctrl+Shift+C."""
    global _enabled
    _enabled = not _enabled
    _save_state()
    message = "Capital beep on" if _enabled else "Capital beep off"
    try:
        presentation_manager.get_manager().present_message(message)
    except Exception as error:
        _log.error("CapitalBeep: could not announce toggle: %s", error)
    _log.info("CapitalBeep: %s", message)
    return True


# --- Public entry point -----------------------------------------------------


def _deferred_setup() -> bool:
    global _player

    wav_path = os.path.join(_DATA_DIR, f"beep_{FREQUENCY_HZ}hz_{DURATION_MS}ms_{FADE_MS}fade.wav")
    if not os.path.isfile(wav_path):
        if not render_wav(wav_path, FREQUENCY_HZ, DURATION_MS, FADE_MS):
            return False
    _player = BeepPlayer(wav_path)

    _install_hooks()
    _log.info("CapitalBeep: ready (enabled=%s, %dHz, %dms)", _enabled, FREQUENCY_HZ, DURATION_MS)
    return False


def install() -> None:
    """Start beeping. Called from the Extension's lifecycle hooks."""
    global _installed
    if _installed:
        return
    _installed = True
    _load_state()
    GLib.idle_add(_deferred_setup)


def uninstall() -> None:
    """Remove every monkey-patch and stop the player.

    Called from the Extension's on_disabled / on_shutdown hooks, so that
    disabling CapitalBeep in Orca's preferences actually stops it and a
    reload does not stack a second set of hooks on the first.
    """
    global _installed, _player
    global _orig_speak, _orig_speak_character
    global _orig_spell_item, _orig_spell_phonetically
    global _orig_sd_char, _orig_sd_speak, _sync_available

    if not _installed:
        return

    _unpatch_all()

    if _player is not None:
        try:
            _player.shutdown()
        except Exception as error:  # pylint: disable=broad-exception-caught
            _log.warning("CapitalBeep: could not shut down the player: %s", error)
        _player = None

    # The _orig_* values double as "already patched" guards, so they have
    # to be cleared too or a later install() would silently do nothing.
    _orig_speak = None
    _orig_speak_character = None
    _orig_spell_item = None
    _orig_spell_phonetically = None
    _orig_sd_char = None
    _orig_sd_speak = None
    _sync_available = False
    _installed = False
    _log.info("CapitalBeep: uninstalled")


# Kept so an orca-customizations.py from before the extension system
# still works.
register = install
