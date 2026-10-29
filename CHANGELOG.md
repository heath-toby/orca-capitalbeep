# Changelog

## 2.3.0

**The caps lock warning moves out, to the add-on whose subject it is.**

It shipped here in 2.2.0 and did not belong: this add-on is about a capital
being *read*, and a caps lock warning is about caps lock being *on*. Toby,
making the call: *"Leave Capital Beep as Capital Beep. Move the caps lock
indicator to caps lock fix."*

It now lives in
[orca-caps-lock-fix](https://github.com/heath-toby/orca-caps-lock-fix) 2.1.0,
with the same three options under the same labels and a fourth that reads each
letter aloud instead of beeping.

### Removed

- The `caps-lock-beep` and `caps-lock-pitch` preferences. The only declared
  preference left is the diagnostics toggle.
- `caps_lock_beep_wanted`, `_beep_caps`, the second player, the caps-lock
  constants and `_NOT_TYPING_MASK`.
- The `KeyboardEvent.__init__` hook, which was the only thing here that
  watched keys rather than speech. Everything that remains hangs off Orca's
  speech path again, which is a cleaner thing for this add-on to be.
- `tests-capslock.py`, whose rows went with the feature — including the one
  that caught 2.2.0's dead Orca-modifier check.

### The two compose

A letter read out by the speaking mode in the other add-on passes through
`SpeechPresenter.speak_character`, which is exactly what this add-on wraps. So
you hear the letter *and* the capital beep that says it is a capital, with no
wiring between the two projects. Toby: *"if it's beeping with each letter, that
can continue connecting with 'these are all capitals', which makes a lot of
sense."*

Nothing else changes. 8 test rows on the audio lifecycle, as before.

## 2.2.1

**The caps lock warning could sound on an Orca command.** Found by a code
review of 2.2.0.

`_NOT_TYPING_MASK` exists to say "a letter arriving with one of these held is
a command, not typing", and its comment singles out the Orca modifier as the
one that matters most, because on the laptop layout that modifier *is*
Caps_Lock. But the hook tested the `modifiers` **argument** the constructor was
called with, and Orca adds its own modifier bit *inside* that constructor:

```python
if modifier_manager.get_pressed_state():
    self.modifiers |= keybindings.ORCA_MODIFIER_MASK
```

So the bit was never present in what was tested, and the whole term was dead
code. The visible symptom, on exactly the setup this was written for: caps lock
on, Caps_Lock as the Orca modifier, press Orca+Shift+H to list headings — with
caps lock on, shift yields a lowercase `h`, which is precisely the pattern the
lowercase warning fires on. The command beeped.

Now reads `self.modifiers`, which is complete by then because the original
constructor has already run. Three test rows: an Orca command does not warn, a
shifted lowercase letter on its own still does, and an event with no mask of
its own falls back to the argument.

Also: the test harness stored live list references and printed them after later
mutation, so a row read `want=[] got=[1]` and truthfully claimed to pass.
Values are snapshotted at comparison time now. 40 rows.

## 2.2.0

**A second, higher tone warns that caps lock is on.**

### Added

- **Warn that caps lock is on**, in Orca Preferences → User Extensions → Capital Beep, with
  three values. The default — *when a lowercase letter is typed, because caps lock is on* —
  is the one NVDA has shipped on by default since about 2010 as "Beep for lowercase with
  Capslock", for the reason it gives: catching caps lock left on by mistake, classically
  while typing a password. The alternative, *on every letter typed while caps lock is on*,
  is noisier but tells you at the first keystroke rather than waiting for you to reach for
  shift — which is what you want at a shell prompt, where a whole command may never need
  shift.

- **Pitch of the caps lock warning**, 1320 Hz by default: an octave above the 660 Hz capital
  beep, so the two cannot be confused. NVDA distinguishes its two beeps the same way and
  uses 3000 Hz, which this setting will take.

- **Caps lock is inferred from the letter that arrived, not read from the lock bit.** Shift
  held and a lowercase letter means caps lock is on; so does an unshifted uppercase one.
  The character that came out is both ground truth and exactly what the warning is about,
  whereas a lock bit has to be the *right* lock bit: on a Wayland session there are two of
  them, the compositor's and XWayland's copy, and which one reaches an add-on depends on
  how the session routes accessibility key events. Reading the character sidesteps that
  entirely, and works on any layout that pairs its cases under shift, Cyrillic included.

- **The first hook in this add-on that watches keys rather than speech.** It has to be:
  with key echo off, nothing in Orca's speech path ever sees the letters being typed.
  `InputEventManager.process_keyboard_event` is the single point every key passes through
  and carries both the modifier mask and the resulting text. Letters pressed with the Orca
  modifier, Control or Alt are commands rather than typing and never warn — not optional on
  the laptop layout, where otherwise every Orca command would look like a letter typed with
  caps lock on.

- **`tests-capslock.py`, 39 rows.** The decision is a pure function, so the whole rule is a
  table. Two of the rows are not about beeping at all: that the hook's signature still
  matches the method it replaces, and that a beep which raises does not swallow the
  keystroke. That hook sits in front of every key Orca handles, and a beep is never worth
  breaking the keyboard for.

### Changed

- **Preferences are now declared**, so the Settings button in User Extensions is live. The
  on/off switch deliberately stays out of it: Orca+Ctrl+Shift+C announces and persists the
  state, and the extension's own enable/disable is already in that pane.

## 2.1.1

**Spelling a word with the Orca keybind no longer raises TypeError on recent Orca.**

### Fixed

- **`spell_item` and `spell_phonetically` hooks accept extra positional args.** Orca's
  `SpeechPresenter.spell_item` and `spell_phonetically` have grown extra parameters
  (`obj`, `start_offset`) that `presentation_manager.py` passes positionally. The old
  hooks were `(self, text)` / `(self, item_string)` only, so every call from the current
  Orca raised `TypeError: _spell_item_hook() takes 2 positional arguments but 4 were
  given`, which killed the whole spell-item path.

  The hooks now accept `*args, **kwargs`. The fallback path in `_spell_item_hook`
  forwards them to the original (preserving upstream behaviour for single-character or
  sync-unavailable cases). The per-character delegation inside both hooks does not
  forward them — the character loop operates on individual characters, where `obj` and
  `start_offset` do not apply, matching the original's own behaviour in its character
  loop.

  Caught by the Monday-morning maintenance agent's signature-compatibility check — the
  same mechanism we built after Polyglot's `update_braille` was broken the same way.

## 2.1.0

**The audio device is released between beeps, which stops the beep vanishing on Bluetooth.**

### Fixed

- **The beep no longer disappears if you hear it often enough.** The pipeline was prerolled
  to `PAUSED` and parked there between beeps, on the reasoning — written in a comment right
  there — that a repeat then needed "only a seek, not a device reopen". That holds the audio
  device open, and a stream held open across many short sounds drifts from an A2DP transport
  until what you hand it lands behind the play point and is discarded. Reading multilingual
  text with a beep on every capital is exactly the workload that triggers it. Wired output
  forgives it entirely, which is why it went unnoticed.

  The pipeline now returns to `NULL` on EOS and `play()` goes `NULL` → `PLAYING`, which
  rewinds the file by itself: the `seek_simple` path and the `_prerolled` flag are gone.

  Orca's own `audio_themes` add-on has always done it this way and never cuts off on
  Bluetooth, however many sounds you ask it for. The companion Indent Beeper add-on had the
  same fault from holding one stream in `PLAYING` and was fixed the same way in its 1.3.0.

### Changed

- **A beep arriving while one is still sounding now interrupts it** rather than queuing
  behind it. That falls out of restarting from `NULL`, and at arrow-key speed it is what you
  want: the beep you care about is the one for the letter you are on.

### Added

- **`tests-player.py`, 8 rows.** The measurement is the interval from `play()` to the
  pipeline reaching `NULL`: a sink posts EOS only after it has played what it was given, so
  that interval is the beep's own length plus the sink's latency — 118–147 ms for an 80 ms
  beep. Anything *shorter* than the beep means the audio was discarded. Restoring the
  `PAUSED` parking turns 6 of the 8 rows red.

## 2.0.0

Packaged as an Orca 51 extension, loaded by Orca's extension system from
`~/.local/share/orca/extensions/capitalbeep/` instead of a block in
`orca-customizations.py`. The rendered WAV and `state.json` stay in
`~/.local/share/orca/capitalbeep/`, outside the package, because Orca hashes every file in
an extension directory.

## 1.0.0

A 660 Hz beep whenever a capital letter is read *as a character* — character navigation,
spelling, phonetic spelling, character and key echo while typing, echo when deleting, and
one-letter words. Reading a whole word or line never beeps, however it is capitalised.
Toggle with Orca+Ctrl+Shift+C.
