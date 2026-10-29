#!/usr/bin/env python3
"""Tests for the caps lock warning's decision logic.

``caps_lock_beep_wanted`` is a pure function of (pressed, modifiers, text,
mode), so the whole rule can be stated as a table and no audio is involved.

The rule infers caps lock from the character that actually arrived rather than
reading the lock bit, which matters here more than most places: on Orca's
laptop layout Caps_Lock *is* the Orca modifier, so the X lock state is not
worth trusting -- and the letter that came out is both ground truth and the
thing the beep is about.

Run after ./install.sh -- it tests the installed package.

Usage: python3 tests-capslock.py
"""

from __future__ import annotations

import os
import sys

import orca.extension_loader  # noqa: F401  (import order: see install.sh)

sys.path.insert(0, os.path.expanduser("~/.local/share/orca/extensions"))

import gi  # noqa: E402
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi  # noqa: E402

from orca import keybindings  # noqa: E402

from capitalbeep import capitalbeep as cb  # noqa: E402

rows, fails = [], 0


def check(name, got, want):
    global fails
    ok = got == want
    if not ok:
        fails += 1
    # Record what was compared, not a reference to it. These tests pass live
    # lists in, and a list appended to later would print its final state beside
    # a verdict reached much earlier -- a row read "want=[] got=[1]" and
    # claimed to pass, which was true and looked like a lie.
    rows.append((name, repr(want), repr(got), "ok" if ok else "FAIL"))


SHIFT = keybindings.SHIFT_MODIFIER_MASK
ORCA = 1 << keybindings.MODIFIER_ORCA
ALT = keybindings.ALT_MODIFIER_MASK
CTRL = 1 << 2
NONE = 0

LOWER, EVERY, OFF = cb.CAPS_MODE_LOWERCASE, cb.CAPS_MODE_EVERY, cb.CAPS_MODE_OFF


def wanted(modifiers, text, mode, pressed=True):
    return cb.caps_lock_beep_wanted(pressed, modifiers, text, mode)


# --- the case the default exists for --------------------------------------
# Shift held and a lowercase letter came out: caps lock is on and has just
# given you the opposite of what you asked for. This is NVDA's case.
check("shift plus a lowercase letter warns, in the default mode",
      wanted(SHIFT, "a", LOWER), True)
check("...and in the every-letter mode too",
      wanted(SHIFT, "a", EVERY), True)

# --- caps lock doing what it says ----------------------------------------
check("an unshifted capital is silent in the default mode",
      wanted(NONE, "A", LOWER), False)
check("...and warns in the every-letter mode",
      wanted(NONE, "A", EVERY), True)

# --- ordinary typing, caps lock off --------------------------------------
check("plain lowercase typing never warns", wanted(NONE, "a", LOWER), False)
check("...not even in the every-letter mode", wanted(NONE, "a", EVERY), False)
check("a properly shifted capital never warns", wanted(SHIFT, "A", LOWER), False)
check("...not even in the every-letter mode", wanted(SHIFT, "A", EVERY), False)

# --- off is off -----------------------------------------------------------
check("the off mode warns for nothing", wanted(SHIFT, "a", OFF), False)
check("...including the unshifted capital", wanted(NONE, "A", OFF), False)

# --- commands are not typing ---------------------------------------------
# This row is the important one on a laptop layout: Caps_Lock is the Orca
# modifier there, so without it every Orca command would look like a letter
# typed with caps lock on.
check("an Orca-modified letter is a command, not typing",
      wanted(ORCA, "a", EVERY), False)
check("...and so is a shifted one", wanted(ORCA | SHIFT, "a", LOWER), False)
check("a control-modified letter is a command", wanted(CTRL, "A", EVERY), False)
check("an alt-modified letter is a command", wanted(ALT, "a", LOWER), False)

# --- only single letters count -------------------------------------------
check("digits do not warn", wanted(SHIFT, "1", EVERY), False)
check("punctuation does not warn", wanted(SHIFT, ",", EVERY), False)
check("space does not warn", wanted(NONE, " ", EVERY), False)
check("a modifier key, which produces no text, does not warn",
      wanted(SHIFT, "", EVERY), False)
check("no text at all does not warn", wanted(SHIFT, None, EVERY), False)
check("a multi-character string does not warn",
      wanted(SHIFT, "ab", EVERY), False)

# --- releases ------------------------------------------------------------
check("a key release never warns",
      wanted(SHIFT, "a", LOWER, pressed=False), False)

# --- not just Latin ------------------------------------------------------
# Toby reads Russian, and Cyrillic pairs its cases under shift exactly as
# Latin does, so the same inference holds.
check("Cyrillic: shift plus a lowercase letter warns",
      wanted(SHIFT, "д", LOWER), True)
check("Cyrillic: an unshifted capital warns in the every-letter mode",
      wanted(NONE, "Д", EVERY), True)
check("Cyrillic: plain lowercase typing does not warn",
      wanted(NONE, "д", LOWER), False)

# --- the settings are read defensively -----------------------------------
cb._settings_source = lambda: {"caps-lock-beep": "nonsense"}
check("an unknown mode falls back to the default", cb._caps_mode(),
      cb.CAPS_MODE_DEFAULT)
cb._settings_source = lambda: {"caps-lock-beep": EVERY}
check("a known mode is honoured", cb._caps_mode(), EVERY)
cb._settings_source = lambda: {"caps-lock-pitch": 99999}
check("an absurd pitch is clamped", cb._caps_pitch(), 8000)
cb._settings_source = lambda: {"caps-lock-pitch": "not a number"}
check("an unusable pitch falls back", cb._caps_pitch(), cb.CAPS_FREQUENCY_HZ)
cb._settings_source = lambda: {}
check("an absent setting falls back to the default",
      cb._caps_mode(), cb.CAPS_MODE_DEFAULT)


def _raises():
    raise RuntimeError("settings unavailable")


cb._settings_source = _raises
check("a settings source that throws falls back rather than breaking the keyboard",
      cb._caps_mode(), cb.CAPS_MODE_DEFAULT)
cb._settings_source = None
check("no settings source at all falls back too",
      cb._caps_mode(), cb.CAPS_MODE_DEFAULT)

# --- the warning is a different sound from the capital beep --------------
check("the warning is pitched well clear of the capital beep",
      cb.CAPS_FREQUENCY_HZ >= cb.FREQUENCY_HZ * 2, True)
check("the default mode is the one NVDA has shipped for years",
      cb.CAPS_MODE_DEFAULT, cb.CAPS_MODE_LOWERCASE)

# --- the hook must never break the keyboard ------------------------------
# This sits in front of every key Orca handles. A signature that does not
# match, or an exception that escapes, does not cost a beep -- it costs the
# keyboard, which for this user is everything.
import inspect  # noqa: E402

from orca import input_event  # noqa: E402

real = inspect.signature(input_event.KeyboardEvent.__init__)
hook = inspect.signature(cb._keyboard_hook)
check("the hook takes the same parameters as the constructor it replaces",
      list(hook.parameters), list(real.parameters))

# Why the constructor rather than InputEventManager.process_keyboard_event,
# which is the obvious seam: on AT-SPI below 2.60, Orca hands
# Atspi.Device.add_key_watcher the *bound* process_keyboard_event at startup,
# so AT-SPI keeps the pre-patch object and a class patch is never called. A
# constructor is looked up on the class when it runs, so it works on both
# AT-SPI paths.
check("this AT-SPI is old enough for that to have mattered",
      Atspi.get_version()[1] < 60, True)

forwarded = []


def _fake_original(self, pressed, keycode, keysym, modifiers, text):
    forwarded.append((pressed, text))


class _Event:
    pass


_saved_original = cb._orig_keyboard_event_init
cb._orig_keyboard_event_init = _fake_original
cb._settings_source = lambda: {"caps-lock-beep": OFF}

cb._keyboard_hook(_Event(), True, 0, 0, SHIFT, "a")
check("the hook builds the event before looking at it",
      forwarded, [(True, "a")])

# And if the beep itself blows up -- no audio device, a GStreamer fault,
# anything -- the key must still get through.
_saved_beep = cb._beep_caps


def _exploding_beep():
    raise RuntimeError("no audio device")


cb._beep_caps = _exploding_beep
cb._settings_source = lambda: {"caps-lock-beep": LOWER}
forwarded.clear()
cb._keyboard_hook(_Event(), True, 0, 0, SHIFT, "a")
check("a beep that raises still leaves the event built",
      forwarded, [(True, "a")])
cb._beep_caps = _saved_beep

# --- the mask tested must be the event's own -----------------------------
# Orca ORs its modifier bit into self.modifiers *inside* the constructor, so
# the bit is never present in the `modifiers` argument. Testing the argument
# made the whole Orca-modifier term of _NOT_TYPING_MASK dead code, and with
# caps lock on, Orca+Shift+H to list headings arrives as a lowercase "h" with
# shift held -- exactly the pattern the lowercase warning fires on. So
# commands beeped.
beeped = []


def _counting_beep():
    beeped.append(1)


cb._beep_caps = _counting_beep
cb._settings_source = lambda: {"caps-lock-beep": LOWER}


class _OrcaModifierEvent:
    """An event whose own mask carries Orca's modifier bit, as Orca's does."""

    def __init__(self):
        self.modifiers = SHIFT | keybindings.ORCA_MODIFIER_MASK


beeped.clear()
cb._keyboard_hook(_OrcaModifierEvent(), True, 0, 0, SHIFT, "h")
check("an Orca command is not a letter typed with caps lock on", beeped, [])

beeped.clear()


class _PlainEvent:
    def __init__(self):
        self.modifiers = SHIFT


cb._keyboard_hook(_PlainEvent(), True, 0, 0, SHIFT, "h")
check("...but a shifted lowercase letter on its own still warns",
      len(beeped), 1)

beeped.clear()
cb._keyboard_hook(_Event(), True, 0, 0, SHIFT, "h")
check("an event with no mask of its own falls back to the argument",
      len(beeped), 1)

cb._beep_caps = _saved_beep
cb._orig_keyboard_event_init = _saved_original
cb._settings_source = None

width = max(len(r[0]) for r in rows)
print()
for name, want, got, status in rows:
    print(f"  {status:4s} {name:<{width}}  want={want}  got={got}")
print(f"\n{len(rows) - fails}/{len(rows)} rows green")
sys.exit(1 if fails else 0)
