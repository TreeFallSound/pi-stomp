"""Tuner audio sources — unit tests for build_source, ToneSweepSource, JackSource guards."""

import math
import time

import numpy as np
import pytest

from pistomp.tuner.source import (
    JackSource,
    ToneSource,
    ToneSweepSource,
    build_source,
)


class TestBuildSource:
    def test_jack_spec(self):
        src = build_source("jack", "system:capture_1", name="test-client")
        assert isinstance(src, JackSource)
        assert src._capture_port == "system:capture_1"

    def test_tone_spec(self):
        src = build_source("tone:440")
        assert isinstance(src, ToneSource)
        assert src._freq == 440.0

    def test_tone_spec_low_freq(self):
        src = build_source("tone:82.41")
        assert isinstance(src, ToneSource)
        assert src._freq == 82.41

    def test_sweep_spec_default_center(self):
        src = build_source("sweep")
        assert isinstance(src, ToneSweepSource)
        assert src._center == 440.0

    def test_sweep_spec_custom_center(self):
        src = build_source("sweep:220")
        assert isinstance(src, ToneSweepSource)
        assert src._center == 220.0

    def test_unknown_spec_raises(self):
        with pytest.raises(ValueError, match="Unknown tuner source spec"):
            build_source("alsa")

    def test_default_name(self):
        src = build_source("jack")
        assert isinstance(src, JackSource)
        assert src._capture_port == "system:capture_1"


class TestJackSourceSampleRateGuard:
    def test_sample_rate_raises_before_start(self):
        src = JackSource()
        with pytest.raises(RuntimeError, match="not available until start"):
            src.sample_rate


class TestToneSource:
    def test_sample_rate_known_at_init(self):
        src = ToneSource(440.0)
        assert src.sample_rate == 48000

    def test_custom_sample_rate(self):
        src = ToneSource(440.0, sample_rate=96000)
        assert src.sample_rate == 96000

    def test_produces_samples(self):
        src = ToneSource(440.0)
        received = []

        def on_samples(block):
            received.append(len(block))

        src.start(on_samples)
        try:
            time.sleep(0.1)
            assert len(received) > 0
        finally:
            src.stop()


class TestToneSweepSource:
    def test_sweep_range(self):
        src = ToneSweepSource(center_hz=440.0)
        min_freq = float("inf")
        max_freq = 0.0
        for t in [0.0, 2.0, 4.0, 6.0]:
            f = src._freq_at(t)
            min_freq = min(min_freq, f)
            max_freq = max(max_freq, f)
        cents_ratio = 1200.0 * math.log2(max_freq / min_freq)
        assert cents_ratio > 100.0  # sweep covers >100 cents

    def test_sweep_period_symmetry(self):
        src = ToneSweepSource(center_hz=440.0)
        f_forward = src._freq_at(2.0)
        f_backward = src._freq_at(6.0)
        assert abs(f_forward - f_backward) < 0.1


