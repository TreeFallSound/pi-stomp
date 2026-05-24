"""Unit tests for EncoderController speed amplification (_compute_multiplier)."""

from unittest.mock import MagicMock

import pytest

from pistomp.encoder_controller import EncoderController


@pytest.fixture
def enc(monkeypatch):
    """Build an EncoderController without GPIO (d_pin=None skips Button setup)."""
    return EncoderController(
        handler=MagicMock(),
        d_pin=None,
        clk_pin=None,
        midi_CC=70,
        midi_channel=0,
        midiout=MagicMock(),
    )


def _clock(monkeypatch, times):
    """Replace time.monotonic with a deterministic iterator over `times` (seconds)."""
    it = iter(times)
    monkeypatch.setattr("pistomp.encoder_controller.time.monotonic", lambda: next(it))


def test_first_tick_returns_min_multiplier(enc, monkeypatch):
    _clock(monkeypatch, [10.0])
    assert enc._compute_multiplier(1) == EncoderController.MIN_MULTIPLIER


def test_zero_rotations_returns_min(enc, monkeypatch):
    _clock(monkeypatch, [10.0, 10.05])
    enc._compute_multiplier(1)
    assert enc._compute_multiplier(0) == EncoderController.MIN_MULTIPLIER


def test_steady_reference_rate_is_unity(enc, monkeypatch):
    # Two detents spaced exactly REFERENCE_DT_MS apart → 1×.
    dt = EncoderController.REFERENCE_DT_MS / 1000.0
    _clock(monkeypatch, [0.0, dt])
    enc._compute_multiplier(1)
    assert enc._compute_multiplier(1) == pytest.approx(EncoderController.MIN_MULTIPLIER)


def test_fast_burst_amplifies(enc, monkeypatch):
    # 4 detents in 20ms ⇒ 5ms/detent ⇒ 80/5 = 16× (clamped at MAX).
    _clock(monkeypatch, [0.0, 0.020])
    enc._compute_multiplier(1)
    m = enc._compute_multiplier(4)
    assert m == pytest.approx(EncoderController.MAX_MULTIPLIER)


def test_slow_spin_stays_at_min(enc, monkeypatch):
    # 1 detent every 500ms — way below reference rate; clamp to MIN.
    _clock(monkeypatch, [0.0, 0.5])
    enc._compute_multiplier(1)
    assert enc._compute_multiplier(1) == EncoderController.MIN_MULTIPLIER


def test_direction_reversal_resets(enc, monkeypatch):
    # Fast forward spin, then reversal → multiplier resets to 1×.
    _clock(monkeypatch, [0.0, 0.010, 0.020])
    enc._compute_multiplier(1)
    fast = enc._compute_multiplier(4)
    assert fast > EncoderController.MIN_MULTIPLIER
    assert enc._compute_multiplier(-1) == EncoderController.MIN_MULTIPLIER


def test_multiplier_clamped_to_max(enc, monkeypatch):
    # Extremely fast: many detents in ~0 time.
    _clock(monkeypatch, [0.0, 0.001])
    enc._compute_multiplier(1)
    assert enc._compute_multiplier(50) == EncoderController.MAX_MULTIPLIER


def test_continuous_curve_between_min_and_max(enc, monkeypatch):
    # 2 detents in 40ms ⇒ 20ms/detent ⇒ 80/20 = 4×.
    _clock(monkeypatch, [0.0, 0.040])
    enc._compute_multiplier(1)
    assert enc._compute_multiplier(2) == pytest.approx(4.0)
