#!/usr/bin/env python3

# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Offline tuner analysis: drive the real TunerEngine over a recorded WAV and
report what the display would show, frame by frame.

This bypasses the live JackSource: it feeds the WAV into the engine's ring
buffer one DSP-hop at a time and calls _process() directly, so the median /
gating / smoothing logic exercised is exactly the on-device path. Use it to
regression-check tuner changes against real plucked-string recordings instead
of guessing — e.g. record an open-string-to-12th-fret-harmonic sweep and watch
for octave excursions, attack settle time, and decay-tail flicker.

Requires the `soundfile` dev dependency (`uv sync`).

Examples:
    uv run python util/tuner_analyze.py recording.wav              # run-length timeline
    uv run python util/tuner_analyze.py recording.wav --mode stats # per-pluck stability
    uv run python util/tuner_analyze.py recording.wav --mode both
"""

import argparse
import os
import sys
from typing import Callable

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import soundfile as sf

from pistomp.tuner.engine import TunerEngine, _freq_to_note


class _WavSource:
    """Minimal AudioSource stand-in exposing only `sample_rate`."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate

    def start(self, on_samples: Callable[[np.ndarray], None]):
        pass

    def stop(self):
        pass


def _run_engine(path):
    """Feed `path` through a real TunerEngine; return (sr, [(t, note, freq_hz), ...])."""
    data, sr = sf.read(path, dtype="float32", always_2d=True)
    x = data.mean(axis=1)  # downmix to mono
    peak = float(np.max(np.abs(x))) or 1.0
    x = (x / peak * 0.7).astype(np.float32)  # normalise to a sane input level

    engine = TunerEngine(_WavSource(sr))
    hop = sr // TunerEngine.DSP_RATE_HZ
    frame_size = TunerEngine.FRAME_SIZE

    samples = []
    pos = 0
    engine._ring.write(x[:frame_size])  # prefill so the first read_latest() succeeds
    while pos + frame_size <= len(x):
        engine._ring.write(x[pos : pos + hop])
        engine._process()
        r = engine.get_reading()
        samples.append((pos / sr, r.note if r else None, r.freq_hz if r else None))
        pos += hop
    return sr, samples


def _segments(samples, min_frames=5):
    """Split into runs of consecutive non-silent frames (a pluck ≈ one segment)."""
    segs, cur = [], []
    for s in samples:
        if s[1] is None:
            if cur:
                segs.append(cur)
                cur = []
        else:
            cur.append(s)
    if cur:
        segs.append(cur)
    return [s for s in segs if len(s) >= min_frames]


def timeline(samples):
    """Run-length view: collapse consecutive identical notes into one line.

    A long stable run = a clean lock. Short interruptions (50-100ms) inside a
    note are the attack/transition blips; a sustained wrong-octave run on a
    fading note is decay-tail flicker.
    """
    print(f"\n{'time':>7}  {'note':>4}  {'frames':>6}  {'dur':>6}   range")
    i = 0
    while i < len(samples):
        j = i
        while j < len(samples) and samples[j][1] == samples[i][1]:
            j += 1
        t0, note, dur = samples[i][0], samples[i][1], j - i
        if note is None:
            print(f"{t0:7.2f}  {'—':>4}  {dur:6d}  {dur * 50:5d}ms   (silence/reject)")
        else:
            freqs = [samples[k][2] for k in range(i, j)]
            print(f"{t0:7.2f}  {note:>4}  {dur:6d}  {dur * 50:5d}ms   {min(freqs):.1f}-{max(freqs):.1f}Hz")
        i = j


def stats(samples):
    """Per-pluck stability: settled note, steady-state jitter, peak-to-peak, worst excursion."""
    segs = _segments(samples)
    print(f"\n{'note':>5}  {'settledHz':>10}  {'jitter(c)':>9}  {'pk-pk(c)':>9}  {'maxExc(c)':>9}")
    worst = 0.0
    for s in segs:
        freqs = [d[2] for d in s]
        settled = float(np.median(freqs[len(freqs) // 3 :]))  # last-two-thirds median
        n = _freq_to_note(settled)
        cents = [1200.0 * np.log2(f / n.ideal_hz) for f in freqs]
        steady = cents[max(1, len(cents) // 3) :]
        excursion = max(abs(c) for c in cents)
        worst = max(worst, excursion)
        print(f"{note:>5}  {settled:10.2f}  {np.std(steady):9.2f}  {max(steady) - min(steady):9.2f}  {excursion:9.1f}")
    print(f"\n  worst excursion across all plucks: {worst:.0f} cents")
    print("  (large maxExc on a single segment is usually a decay-tail/transition blip,")
    print("   not steady-state — cross-check with --mode timeline)")


def main():
    ap = argparse.ArgumentParser(description="Analyse a tuner recording through the real TunerEngine.")
    ap.add_argument("wav", help="path to a mono/stereo WAV recording of plucked notes")
    ap.add_argument("--mode", choices=["timeline", "stats", "both"], default="timeline")
    args = ap.parse_args()

    sr, samples = _run_engine(args.wav)
    print(f"# {args.wav}")
    print(
        f"# sr={sr}  median_len={TunerEngine.MEDIAN_LEN}  dsp_rate={TunerEngine.DSP_RATE_HZ}Hz"
        f"  frame={TunerEngine.FRAME_SIZE}"
    )
    if args.mode in ("timeline", "both"):
        timeline(samples)
    if args.mode in ("stats", "both"):
        stats(samples)


if __name__ == "__main__":
    main()
