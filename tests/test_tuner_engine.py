"""Tuner engine — unit tests for freq_to_note and integration tests with ToneSource."""

import math
import time

import numpy as np
import pytest

from pistomp.tuner.engine import TunerEngine, TunerReading, _freq_to_note
from pistomp.tuner.source import ToneSource


class TestFreqToNote:
    def test_a4(self):
        name, cents, ideal = _freq_to_note(440.0)
        assert name == "A4"
        assert abs(cents) < 0.5
        assert abs(ideal - 440.0) < 0.1

    def test_c4(self):
        name, cents, ideal = _freq_to_note(261.63)
        assert name == "C4"
        assert abs(cents) < 1.0

    def test_low_e_string(self):
        name, cents, ideal = _freq_to_note(82.41)
        assert name == "E2"
        assert abs(cents) < 1.5

    def test_sharp_note(self):
        name, cents, ideal = _freq_to_note(466.16)
        assert name.startswith("A")
        assert "\u266f" in name or name == "Bb4"

    def test_cents_sharp(self):
        _, cents, _ = _freq_to_note(445.0)
        assert cents > 10.0

    def test_cents_flat(self):
        _, cents, _ = _freq_to_note(435.0)
        assert cents < -10.0

    def test_ideal_hz_matches_note(self):
        name, _, ideal = _freq_to_note(220.0)
        assert name == "A3"
        assert abs(ideal - 220.0) < 0.1

    def test_very_low_frequency(self):
        name, cents, ideal = _freq_to_note(32.7)
        assert "C" in name


class TestTunerEngineIntegration:
    def test_tone_440_produces_a4(self):
        src = ToneSource(440.0)
        engine = TunerEngine(src)
        engine.start()
        try:
            deadline = time.monotonic() + 3.0
            reading = None
            while time.monotonic() < deadline:
                reading = engine.get_reading()
                if reading is not None:
                    break
                time.sleep(0.05)
            assert reading is not None
            assert reading.note == "A4"
            assert abs(reading.cents) < 10.0
        finally:
            engine.stop()

    def test_tone_220_produces_a3(self):
        src = ToneSource(220.0)
        engine = TunerEngine(src)
        engine.start()
        try:
            deadline = time.monotonic() + 3.0
            reading = None
            while time.monotonic() < deadline:
                reading = engine.get_reading()
                if reading is not None:
                    break
                time.sleep(0.05)
            assert reading is not None
            assert "A" in reading.note
        finally:
            engine.stop()

    def test_reading_becomes_stale_after_stop(self):
        src = ToneSource(440.0)
        engine = TunerEngine(src)
        engine.start()
        time.sleep(1.0)
        reading = engine.get_reading()
        assert reading is not None
        engine.stop()
        time.sleep(0.1)
        remaining = engine.get_reading()
        # The last reading persists but becomes stale
        if remaining is not None:
            assert remaining.ts < time.monotonic() - 0.1

    def test_reading_is_frozen_dataclass(self):
        reading = TunerReading(note="A4", cents=0.0, freq_hz=440.0, ideal_hz=440.0, ts=time.monotonic())
        with pytest.raises(AttributeError):
            reading.note = "B4"  # type: ignore[misc]

    def test_engine_stop_is_idempotent(self):
        src = ToneSource(440.0)
        engine = TunerEngine(src)
        engine.start()
        time.sleep(0.5)
        engine.stop()
        engine.stop()