#!/usr/bin/env python3
"""Quick YIN sanity-check. Run with: uv run python test_yin.py"""

import math
import numpy as np
from pistomp.tuner.yin import detect_pitch
from pistomp.tuner.ringbuffer import RingBuffer

SAMPLE_RATE = 48000
FRAME_SIZE = 4096
BLOCK_SIZE = 256  # matches ToneSweepSource.BLOCK_SIZE


def make_triangle(freq: float, n: int = FRAME_SIZE, sr: int = SAMPLE_RATE) -> np.ndarray:
    phase = np.arange(n, dtype=np.float64)
    period = sr / freq
    return (1.0 - 4.0 * np.abs((phase % period) / period - 0.5)).astype(np.float32)


def make_sine(freq: float, n: int = FRAME_SIZE, sr: int = SAMPLE_RATE) -> np.ndarray:
    t = np.arange(n, dtype=np.float64) / sr
    return np.sin(2 * math.pi * freq * t).astype(np.float32)


def cents(detected: float, expected: float) -> float:
    return 1200 * math.log2(detected / expected)


def flag(err_cents: float, warn: float = 10.0, bad: float = 20.0) -> str:
    if abs(err_cents) >= bad:
        return "  <-- BAD"
    if abs(err_cents) >= warn:
        return "  <-- warn"
    return ""


# ---------------------------------------------------------------------------
# Fixed pitches — sine and square across the guitar range
# ---------------------------------------------------------------------------
print(f"{'wave':<6} {'expected Hz':>12} {'detected Hz':>12} {'cents err':>10}")
print("-" * 46)

for freq in [41.2, 55.0, 82.4, 110.0, 146.8, 196.0, 220.0, 246.9, 329.6, 392.0, 440.0, 587.3, 659.3, 880.0, 1046.5, 1174.7]:
    for label, frame in [("sine", make_sine(freq)), ("tri", make_triangle(freq))]:
        result = detect_pitch(frame, SAMPLE_RATE, freq_min=30.0)
        if result is None:
            print(f"{label:<6} {freq:>12.1f} {'None':>12}")
        else:
            err = cents(result, freq)
            print(f"{label:<6} {freq:>12.1f} {result:>12.2f} {err:>+10.1f}{flag(err)}")


def run_sweep(
    label: str,
    center_hz: float,
    sweep_cents: float = 60.0,
    sweep_period: float = 8.0,
    dsp_rate: float = 20.0,
    steps: int = 60,
    wave: str = "tri",
) -> None:
    """
    Simulate production: generate audio in BLOCK_SIZE blocks with continuous
    phase, write to a RingBuffer, read FRAME_SIZE samples per DSP tick.
    """
    print()
    print(f"Sweep ({wave}, {center_hz:.1f} Hz centre ±{sweep_cents:.0f} cents, {sweep_period:.0f}s period):")
    print(f"{'t (s)':>8} {'expected Hz':>12} {'detected Hz':>12} {'cents err':>10}")
    print("-" * 46)

    ring = RingBuffer(16384)
    frame_buf = np.zeros(FRAME_SIZE, dtype=np.float32)

    dsp_interval = 1.0 / dsp_rate
    blocks_per_dsp = max(1, int(dsp_interval * SAMPLE_RATE / BLOCK_SIZE))

    phase = 0.0
    t_elapsed = 0.0

    for step in range(steps):
        t_report = step * dsp_interval

        # Generate blocks_per_dsp chunks at the current sweep position
        for _ in range(blocks_per_dsp):
            freq_at_block = center_hz * math.pow(
                2.0,
                sweep_cents * (2.0 * (1.0 - abs(2.0 * ((t_elapsed % sweep_period) / sweep_period) - 1.0)) - 1.0) / 1200.0,
            )
            period = SAMPLE_RATE / freq_at_block
            buf = np.empty(BLOCK_SIZE, dtype=np.float32)
            for i in range(BLOCK_SIZE):
                if wave == "sine":
                    buf[i] = math.sin(2 * math.pi * phase / period)
                else:
                    buf[i] = 1.0 - 4.0 * abs((phase % period) / period - 0.5)
                phase += 1.0
            ring.write(buf)
            t_elapsed += BLOCK_SIZE / SAMPLE_RATE

        # Expected freq at the reporting instant
        p = (t_report % sweep_period) / sweep_period
        tri = 1.0 - abs(2.0 * p - 1.0)
        c = sweep_cents * (2.0 * tri - 1.0)
        expected = center_hz * math.pow(2.0, c / 1200.0)

        if not ring.read_latest(FRAME_SIZE, frame_buf):
            print(f"{t_report:>8.2f} {expected:>12.2f} {'(buffering)':>12}")
            continue

        result = detect_pitch(frame_buf, SAMPLE_RATE)
        if result is None:
            print(f"{t_report:>8.2f} {expected:>12.2f} {'None':>12}")
        else:
            err = cents(result, expected)
            print(f"{t_report:>8.2f} {expected:>12.2f} {result:>12.2f} {err:>+10.1f}{flag(err)}")


# Standard guitar tuning sweep — each open string
run_sweep("E2 low",  center_hz=82.4,  sweep_cents=60.0, steps=40)
run_sweep("A2",      center_hz=110.0, sweep_cents=60.0, steps=40)
run_sweep("D3",      center_hz=146.8, sweep_cents=60.0, steps=40)
run_sweep("G3",      center_hz=196.0, sweep_cents=60.0, steps=40)
run_sweep("B3",      center_hz=246.9, sweep_cents=60.0, steps=40)
run_sweep("E4 high", center_hz=329.6, sweep_cents=60.0, steps=40)

# Wide sweep
run_sweep("A2 wide", center_hz=110.0, sweep_cents=150.0, steps=40)

# High register
run_sweep("A5",      center_hz=880.0, sweep_cents=40.0,  steps=40)

# Slow sweep
run_sweep("E2 slow", center_hz=82.4,  sweep_cents=60.0, sweep_period=20.0, steps=40)

# Sine sweeps for comparison
run_sweep("E2 sine", center_hz=82.4,  sweep_cents=60.0, steps=40, wave="sine")
run_sweep("A5 sine", center_hz=880.0, sweep_cents=40.0,  steps=40, wave="sine")
