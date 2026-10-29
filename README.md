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

There is no settings dialog of its own, by design: the on/off switch is this
keystroke, and the enable/disable is already in **Orca Preferences → User
Extensions → Capital Beep**, where a diagnostics toggle is also declared.

**The caps lock warning moved out in 2.3.0.** A higher tone for "caps lock is
on" shipped here in 2.2.0 and did not belong: this add-on is about a capital
being *read*, and that is about caps lock being *on*. It now lives in
[orca-caps-lock-fix](https://github.com/heath-toby/orca-caps-lock-fix), whose
subject it is, with the same three options under the same labels and a fourth
that reads each letter aloud instead of beeping. The two add-ons compose: a
letter read out by that one still carries this one's capital beep, so you hear
the letter *and* the tone that says it is a capital.

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

