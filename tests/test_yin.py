"""YIN pitch detection — unit tests with synthetic signals."""

import numpy as np
import pytest

from pistomp.tuner.yin import PitchEstimate, detect_pitch

_SR = 48000


def _sine(freq: float, duration: float = 0.2, sr: int = _SR) -> np.ndarray:
    t = np.arange(int(sr * duration), dtype=np.float64) / sr
    return (0.8 * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)


def _silence(n: int = _SR // 5, sr: int = _SR) -> np.ndarray:
    return np.zeros(n, dtype=np.float32)


class TestDetectPitchSine:
    def test_a4_440hz(self):
        frame = _sine(440.0)
        est = detect_pitch(frame, _SR)
        assert est is not None
        assert abs(est.freq - 440.0) < 1.0

    def test_e3_164hz(self):
        frame = _sine(164.81)
        est = detect_pitch(frame, _SR)
        assert est is not None
        assert abs(est.freq - 164.81) < 1.5

    def test_c4_261hz(self):
        frame = _sine(261.63)
        est = detect_pitch(frame, _SR)
        assert est is not None
        assert abs(est.freq - 261.63) < 2.0

    def test_low_e_82hz(self):
        frame = _sine(82.41, duration=0.5)
        est = detect_pitch(frame, _SR)
        assert est is not None
        assert abs(est.freq - 82.41) < 2.0

    def test_high_a_880hz(self):
        frame = _sine(880.0, duration=0.4)
        est = detect_pitch(frame, _SR)
        assert est is not None
        assert abs(est.freq - 880.0) < 15.0  # YIN can have octave errors at high freq

    def test_cents_accuracy(self):
        freq = 443.0  # ~11.7 cents sharp of A4
        frame = _sine(freq)
        est = detect_pitch(frame, _SR)
        assert est is not None
        assert abs(est.freq - freq) < 5.0  # YIN with short frame is approximate
        assert est.yin_error < 0.15


class TestDetectPitchSilence:
    def test_silence_returns_none(self):
        frame = _silence()
        est = detect_pitch(frame, _SR)
        assert est is None

    def test_near_silence_returns_none(self):
        frame = np.full(_SR // 5, 1e-5, dtype=np.float32)
        est = detect_pitch(frame, _SR)
        assert est is None


class TestDetectPitchWindow:
    def test_explicit_window(self):
        frame = _sine(440.0, duration=0.3)
        window = 4096
        est = detect_pitch(frame, _SR, window=window)
        assert est is not None
        assert abs(est.freq - 440.0) < 1.5

    def test_window_shorter_than_half(self):
        frame = _sine(440.0, duration=0.2)
        est_short = detect_pitch(frame, _SR, window=2048)
        assert est_short is not None
        assert abs(est_short.freq - 440.0) < 2.0


class TestDetectPitchFreqBounds:
    def test_low_cutoff(self):
        frame = _sine(20.0, duration=0.5)
        est = detect_pitch(frame, _SR, freq_min=30.0)
        assert est is None

    def test_high_cutoff(self):
        frame = _sine(5000.0)
        est = detect_pitch(frame, _SR, freq_max=1000.0)
        # YIN may find a sub-harmonic within freq_max for very high inputs;
        # what we really assert is it doesn't report ~5000
        if est is not None:
            assert est.freq <= 1000.0


class TestPitchEstimate:
    def test_frozen_dataclass(self):
        p = PitchEstimate(freq=440.0, yin_error=0.05)
        assert p.freq == 440.0
        with pytest.raises(AttributeError):
            p.freq = 441.0  # type: ignore[misc]