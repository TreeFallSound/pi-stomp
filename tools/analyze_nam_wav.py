#!/usr/bin/env python3
"""Analyze the NAM reamp WAV level in dBFS, one row per second.

Flags chunks that fall below the capture session's silence threshold so you
can see which sections risk a false silence-abort during training.

Usage:
    uv run python3 tools/analyze_nam_wav.py [path/to/wav]
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

_DEFAULT_WAV = Path(__file__).resolve().parents[1] / "setup" / "nam" / "T3K-sweep-v3.wav"
_SAMPLE_RATE = 48000
_SILENCE_SETTLE_S = 2  # mirrors capture_session.py
_SILENCE_INPUT_THRESHOLD = 1e-2  # mirrors capture_session.py  (≈ −40 dBFS)
_SILENCE_PLAY_THRESHOLD = 0.1  # mirrors capture_session.py  (≈ −20 dBFS)
_CLIP_THRESHOLD = 0.99  # mirrors capture_session.py


def peak_dbfs(chunk: np.ndarray) -> float:
    peak = float(np.max(np.abs(chunk)))
    if peak == 0.0:
        return -math.inf
    return 20.0 * math.log10(peak)


def bar(dbfs: float, width: int = 40) -> str:
    """ASCII bar: maps [−60, 0] dBFS onto *width* characters."""
    if math.isinf(dbfs):
        filled = 0
    else:
        filled = int(max(0.0, min(1.0, (dbfs + 60.0) / 60.0)) * width)
    return "█" * filled + "░" * (width - filled)


def main() -> None:
    wav_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_WAV
    if not wav_path.exists():
        sys.exit(f"WAV not found: {wav_path}")

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pistomp.nam.wavio import load_wav_float32

    samples = load_wav_float32(wav_path)
    duration = len(samples) / _SAMPLE_RATE
    chunk_size = _SAMPLE_RATE  # 1 second

    input_dbfs = 20.0 * math.log10(_SILENCE_INPUT_THRESHOLD)
    play_dbfs = 20.0 * math.log10(_SILENCE_PLAY_THRESHOLD)
    clip_dbfs = 20.0 * math.log10(_CLIP_THRESHOLD)

    print(f"File    : {wav_path.name}")
    print(f"Duration: {duration:.1f} s  ({len(samples):,} frames @ {_SAMPLE_RATE} Hz)")
    print(
        f"Thresholds: play gate >= {play_dbfs:.0f} dBFS | silence < {input_dbfs:.0f} dBFS "
        f"(after {_SILENCE_SETTLE_S} s settle) | clip >= {clip_dbfs:.2f} dBFS"
    )
    print()
    print(f"{'Time':>6}  {'Peak dBFS':>9}  {'':40}  Notes")
    print("-" * 72)

    for i, start in enumerate(range(0, len(samples), chunk_size)):
        chunk = samples[start : start + chunk_size]
        t = i  # seconds
        db = peak_dbfs(chunk)

        notes = []
        if db >= clip_dbfs:
            notes.append("CLIP")
        elif db < play_dbfs:
            notes.append("below play gate (silence detection frozen)")
        elif t >= _SILENCE_SETTLE_S and db < input_dbfs:
            notes.append("< silence threshold")

        db_str = f"{db:+.1f}" if not math.isinf(db) else "  -inf"
        print(f"{t:5d}s  {db_str:>9}  {bar(db)}  {', '.join(notes)}")

    print()
    quiet_chunks = sum(
        1
        for i, start in enumerate(range(0, len(samples), chunk_size))
        if i >= _SILENCE_SETTLE_S and peak_dbfs(samples[start : start + chunk_size]) < input_dbfs
    )
    print(f"{quiet_chunks} second(s) below silence threshold after settle window (need 2 consecutive to abort).")


if __name__ == "__main__":
    main()
