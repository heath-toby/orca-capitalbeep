# CapitalBeep for Orca

A short tone whenever a capital letter is read as a character.

Orca's capitalization styles each leave a gap. **Icon** plays a tone for every
capital everywhere, which is more than most people want. **Spell** says "cap"
before the letter, but it costs you the lovely behaviour where a fully
capitalised line is read in the capitals pitch. **Pitch change** keeps that line
behaviour, but with some voices the pitch shift is inaudible on letters like S,
U and O, so `s` and `S` sound identical while arrowing through text.

CapitalBeep is meant to sit alongside **pitch change**. You keep the whole-line
behaviour, and get an unmistakable 80 ms tone on the individual capitals that
pitch alone does not disambiguate.

## The rule

A unit of exactly one uppercase letter, read as a unit, beeps:

- character navigation, in caret navigation and in flat review
- spelling, including phonetic spelling
- character and key echo while typing, and echo when deleting
- a word that is a single letter, such as "I" or "A"

Reading a whole word or line never beeps, however it is capitalised. "is" and
"IS" are both silent, because neither is read one character at a time.

## Install

    ./install.sh
    orca --replace &

To remove it again:

    ./uninstall.sh
    orca --replace &

`install.sh` copies the package to
`$XDG_DATA_HOME/orca/extensions/capitalbeep` and approves it with
`orca --approve-extension`. Orca re-checks the hash of every file in the package
on each start, so re-run the installer after editing anything.

## Use

Press **Orca+Ctrl+Shift+C** to toggle the beep. The setting persists across
restarts.

There is no settings dialog of its own, by design. The two caps lock settings
below are *declared* to Orca and appear in **Orca Preferences → User
Extensions → Capital Beep**, which costs no dialog code and keeps the on/off
switch where it already is.

## Tuning

Three constants at the top of `capitalbeep/capitalbeep.py`:

- `FREQUENCY_HZ` — 660 by default, which is E5. A5 would be 880.
- `DURATION_MS` — 80 by default.
- `VOLUME_HEADROOM` — 0.35 by default. The beep tracks Orca's own speech volume,
  scaled by this. A full-scale sine is much louder than speech at the same
  nominal setting, so raise or lower this one number to balance the beep against
  your voice.

The tone is rendered to a small WAV on first run and cached; the filename encodes
the frequency, duration and fade, so changing any of them regenerates it.

## How it works

This is an Orca 51 user extension, and it hooks a few of Orca's internals from
its `on_ready`. Every hook is individually guarded, so if a future Orca release
moves something, Orca still starts normally and the `orca-capitalbeep` logger
says what failed to attach.

- Characters need no gating: `orca.speech.speak_character` is the single point
  every individually-read character passes through, covering navigation, flat
  review, spelling, key echo, typing echo and deletion echo at once.
- Words are gated, because `orca.speech.speak` also carries lines and phrases.
  `say_word` and flat review's `_item_presentation` arm the gate, and only a
  single-letter payload inside it beeps.
- Phonetic spelling gets an explicit beep, because `get_phonetic_name()`
  lowercases its input: "alpha" is spoken for both `a` and `A`, so there is
  nothing left in the text to detect.
- Spelling beeps are synchronised through Speech Dispatcher. Orca queues every
  spelled character without waiting, so beeping as each is queued would put them
  all in a burst up front. Instead each capital hangs a BEGIN callback on its own
  queued message and beeps the instant that letter starts being spoken. Without
  python-speechd this degrades to beeping immediately.
- The tone is a pre-rendered WAV with a raised-cosine fade rather than a gated
  sine, which would click at the cut. The GStreamer pipeline stays prerolled and
  is re-seeked, so fast typing does not reopen the audio device.

## Requirements

- Orca 50.x (developed against 50.2)
- GStreamer with Python bindings
- python-speechd, optional, for synchronised spelling beeps

## Licence

GPL-2.0-or-later, matching Orca.

## Why the pipeline closes after every beep

The beep's pipeline is driven `PLAYING` for each beep and returned to `NULL`
when it ends, so the audio device is released between beeps. It used to be
prerolled to `PAUSED` and parked there, on the reasoning that a repeat then
needed only a seek rather than a device reopen.

That reasoning costs you the beep on Bluetooth. A stream held open across many
short sounds drifts from an A2DP transport until what you hand it lands behind
the play point and is discarded — so the beep vanishes if you hear it often
enough, which reading multilingual text with a beep on every capital certainly
is. Wired output forgives it entirely, which is why it took a while to notice.

Orca's own `audio_themes` add-on has always done it the right way: back to
`NULL` on EOS, and it plays as many sounds as you like on A2DP without cutting
off. The Indent Beeper add-on had the same fault from holding one stream open
and was fixed the same way.

Two side effects, both wanted: a beep arriving while one is still sounding
interrupts it rather than queuing behind it, and nothing is carried from one
beep to the next.

## Tests

```
./install.sh && python3 tests-player.py
```

Eight rows, no recording needed. The measurement is the interval from `play()`
to the pipeline reaching `NULL`: a sink posts EOS only after it has played what
it was given, so that interval is the beep's length plus the sink's latency.
Shorter than the beep means the audio was discarded — which is how the sibling
add-on was silenced for one build, by handing the sink a clip with no duration.

## The caps lock warning

A second, higher tone warns that caps lock is on. **Orca Preferences → User
Extensions → Capital Beep** has two settings for it:

1. **Warn that caps lock is on** —
   - *When a lowercase letter is typed, because caps lock is on* (the default).
     You held shift, caps lock was already on, and you got the opposite of what
     you asked for. NVDA has shipped exactly this, on by default, since about
     2010, under the name "Beep for lowercase with Capslock"; its purpose is to
     catch caps lock left on by mistake, classically while typing a password.
   - *On every letter typed while caps lock is on.* Noisier, but it tells you
     caps lock is on the moment you start typing rather than waiting for you to
     reach for shift — useful at a shell prompt, where you may type a whole
     command without ever pressing shift.
   - *Never.*
2. **Pitch of the caps lock warning** — 1320 Hz by default, an octave above the
   660 Hz capital beep so the two cannot be confused. Set it to 3000 for
   NVDA's exact sound.

### How caps lock is detected

Not from the lock bit. The add-on works it out from the letter that actually
arrived: shift held and a lowercase letter means caps lock is on, as does an
unshifted uppercase one. That is deliberate — on Orca's **laptop** keyboard
layout `Caps_Lock` *is* the Orca modifier, so the X lock state is not a thing
worth trusting, while the character that came out is both ground truth and
exactly what the warning is about. It also means the warning works on any
layout that pairs its cases under shift, Cyrillic included.

Letters pressed with the Orca modifier, Control or Alt are commands rather than
typing and never warn. That first exclusion is not optional on the laptop
layout: without it every Orca command would look like a letter typed with caps
lock on.

### Why it hooks keys and not speech

Everything else in this add-on hangs off Orca's speech path. The caps lock
warning cannot: with **key echo off**, nothing in that path ever sees the
letters being typed. So it wraps `InputEventManager.process_keyboard_event`,
the single point every key passes through, which carries both the modifier mask
and the text the key produced.

That hook sits in front of every keystroke Orca handles, so it is written to be
impossible to trip over: anything raised inside it is swallowed and the key is
forwarded regardless. `tests-capslock.py` asserts both that its signature still
matches the method it replaces and that a beep which throws does not swallow
the keystroke.

## Tests

```
./install.sh && python3 tests-player.py && python3 tests-capslock.py
```

- `tests-player.py` — 8 rows on the audio lifecycle. The measurement is the
  interval from `play()` to the pipeline reaching `NULL`: that is the beep's own
  length plus the sink's latency, and anything shorter means the audio was
  discarded.
- `tests-capslock.py` — 39 rows on the warning's decision logic, which is a
  pure function and so can be stated as a table, plus the keyboard-safety rows
  above.
