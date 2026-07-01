"""Unit tests for the compressor GR engine's derivation math.

Uses the synthetic PairedToneSource (no JACK) so the arithmetic is exercised
headlessly, mirroring how the tuner engine is tested against tone sources.
"""

from __future__ import annotations

import time

from pistomp.compmeter.engine import GrEngine
from pistomp.compmeter.source import PairedToneSource


def _settle(engine: GrEngine, seconds: float = 0.4):
    engine.start()
    time.sleep(seconds)
    reading = engine.get_reading()
    engine.stop()
    assert reading is not None
    return reading


def test_gr_recovers_output_attenuation():
    # Output is 6 dB below input, no makeup → GR should read ~6 dB.
    r = _settle(GrEngine(PairedToneSource(out_gain_db=-6.0), makeup_db=0.0))
    assert r.valid
    assert 5.0 < r.gr_db < 7.0
    assert r.in_db - r.out_db == 6.0 or abs((r.in_db - r.out_db) - 6.0) < 0.5


def test_makeup_is_subtracted_from_gr():
    # Net output gain 0 dB but the compressor is applying +6 makeup, so the
    # actual downward compression is 6 dB. Engine told makeup=6 → GR ~6.
    r = _settle(GrEngine(PairedToneSource(out_gain_db=0.0), makeup_db=6.0))
    assert r.valid
    assert 5.0 < r.gr_db < 7.0


def test_silence_is_invalid():
    # Near-silent input → reading marked invalid, GR pinned to 0.
    r = _settle(GrEngine(PairedToneSource(in_amp=1e-5, out_gain_db=-6.0)))
    assert not r.valid
    assert r.gr_db == 0.0
