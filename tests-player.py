#!/usr/bin/env python3
"""Tests for CapitalBeep's player: does the beep sound, and is the device freed?

One number answers both, and it needs no recording: a sink posts EOS only
after it has played what it was given, and the EOS handler closes the device.
So the interval from play() to the pipeline reaching NULL is the beep's own
length plus the sink's latency. Shorter than the beep means the audio was
discarded -- which is exactly how the sibling indent-beeper add-on was
silenced for one build, by handing the sink a clip with no duration.

Why it matters that the device is freed at all: holding it open across many
short beeps drifts from a Bluetooth transport until what you hand it lands
behind the play point and is dropped. Toby: "the tone can just vanish
altogether if you hear the beep too often."

Run after ./install.sh -- it tests the installed package.

Usage: python3 tests-player.py
"""

from __future__ import annotations

import os
import sys
import time
import wave

import orca.extension_loader  # noqa: F401  (import order: see install.sh)

sys.path.insert(0, os.path.expanduser("~/.local/share/orca/extensions"))

import gi  # noqa: E402
gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # noqa: E402

from capitalbeep import tone  # noqa: E402

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


DATA = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "orca", "capitalbeep")
WAV = os.path.join(DATA, "beep_660hz_80ms_8fade.wav")
if not os.path.isfile(WAV):
    tone.render_wav(WAV, 660, 80, 8)
with wave.open(WAV) as handle:
    beep_ms = handle.getnframes() / handle.getframerate() * 1000

context = GLib.MainContext.default()


def wait_for_null(player, seconds=2.5):
    """Milliseconds until the device is closed, or None."""
    start = time.monotonic()
    while time.monotonic() - start < seconds:
        while context.pending():
            context.iteration(False)
        if player._pipeline is None:
            return None
        if player._pipeline.get_state(0)[1] == Gst.State.NULL:
            return (time.monotonic() - start) * 1000
        time.sleep(0.005)
    return None


player = tone.BeepPlayer(WAV)
check("the device is not held before the first beep",
      player._pipeline.get_state(0)[1], Gst.State.NULL)
check("nothing is prerolled any more", hasattr(player, "_prerolled"), False)

start = time.monotonic()
player.play(0.4)
closed = wait_for_null(player)
check("the beep plays and the device closes afterwards", closed is not None, True)
check("...only after the beep has had time to sound",
      closed is not None and closed > beep_ms, True)

player.play(0.4)
check("a second beep reuses the pipeline and closes again",
      wait_for_null(player) is not None, True)

# A beep arriving over one still sounding takes over, which is what you want
# at arrow-key speed.
player.play(0.4)
time.sleep(0.02)
player.play(0.4)
check("a beep over a sounding one is accepted and still finishes",
      wait_for_null(player) is not None, True)

player.shutdown()
check("shutdown drops the pipeline", player._pipeline, None)
check("...and playing afterwards is a no-op, not a crash",
      player.play(0.4), None)

width = max(len(r[0]) for r in rows)
print()
for name, want, got, status in rows:
    print(f"  {status:4s} {name:<{width}}  want={want}  got={got}")
print(f"\n{len(rows) - fails}/{len(rows)} rows green  "
      f"(beep is {beep_ms:.0f} ms)")
sys.exit(1 if fails else 0)
