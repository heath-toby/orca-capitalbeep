# Changelog

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
