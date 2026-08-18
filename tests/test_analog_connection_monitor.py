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

"""Monte Carlo tests for AnalogConnectionMonitor.

The physical stream generators below model the actual electrical
signatures measured on a pi-Stomp v2 core (MCP3008, 3.3 V, 100 Hz poll):

  FLOATING        — 60 Hz mains hum cap-coupled onto a high-impedance
                    pin. At 100 Hz sample rate the 60 Hz aliases to a
                    ~40 Hz beat. Measured: sigma ≈ 23 LSB, E up to 96 LSB,
                    mean wanders ±45 LSB over 60 s. Modeled as a
                    Gaussian-modulated sinusoid.
  CONNECTED_REST  — passive pot at rest. Johnson + kTC noise < 1 LSB.
                    Measured sigma ≈ 0.4 LSB, E ≈ 2 LSB. Modeled as
                    value + Gaussian(0, 0.4), rounded, clipped.
  CONNECTED_MOVING— wiper in motion. Clean monotonic sweep + sub-LSB
                    noise. Modeled as linspace + Gaussian(0, 0.4).
  PLUGIN           — floating stream, then step to CONNECTED_REST at
                     a given value at a given index.
  UNPLUG           — CONNECTED_REST, then transition to FLOATING.

All trials use sequential fixed seeds for reproducibility.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pistomp.input.analog_connection import AnalogConnectionMonitor, AnalogConnectionState

ADC_MAX = 1023


# ─── Physical stream generators ──────────────────────────────────────


def floating_stream(
    n: int,
    rng: np.random.Generator,
    *,
    mean: float = 16.0,
    hum_amp: float = 23.0,
    beat_freq: float = 0.07,
    noise_std: float = 6.0,
) -> np.ndarray:
    """Model a floating ADC pin: 60 Hz mains hum aliased at 100 Hz poll.

    The aliased 60 Hz appears as a slow beat (freq ≈ 0.07 Hz/sample for
    a ~14 s period, matching the measured wander). A Gaussian envelope
    adds sample-to-sample jitter.
    """
    t = np.arange(n, dtype=np.float64)
    beat = mean + hum_amp * np.sin(2 * np.pi * beat_freq * t / n * 8)
    noise = rng.normal(0, noise_std, n)
    return np.clip(np.round(beat + noise), 0, ADC_MAX).astype(int)


def connected_at_rest(n: int, value: float, rng: np.random.Generator, *, sigma: float = 0.4) -> np.ndarray:
    """Model a connected passive pot, stationary, at `value`."""
    return np.clip(np.round(value + rng.normal(0, sigma, n)), 0, ADC_MAX).astype(int)


def connected_moving(n: int, v0: float, v1: float, rng: np.random.Generator, *, sigma: float = 0.4) -> np.ndarray:
    """Model a connected pot swept from v0 to v1 over n samples."""
    sweep = np.linspace(v0, v1, n)
    return np.clip(np.round(sweep + rng.normal(0, sigma, n)), 0, ADC_MAX).astype(int)


def plugin_event(n_float: int, plug_value: float, rng: np.random.Generator, *, n_post: int = 400) -> np.ndarray:
    """Floating for n_float samples, then connected-at-rest at plug_value."""
    pre = floating_stream(n_float, rng)
    post = connected_at_rest(n_post, plug_value, rng)
    return np.concatenate([pre, post])


def unplug_event(conn_value: float, n_conn: int, rng: np.random.Generator, *, n_float: int = 400) -> np.ndarray:
    """Connected-at-rest for n_conn samples, then floating."""
    pre = connected_at_rest(n_conn, conn_value, rng)
    post = floating_stream(n_float, rng)
    return np.concatenate([pre, post])


# ─── Helpers ─────────────────────────────────────────────────────────


def _run_stream(stream: np.ndarray) -> AnalogConnectionMonitor:
    """Feed an entire stream into a fresh monitor, return the monitor."""
    mon = AnalogConnectionMonitor()
    for raw in stream:
        mon.observe(int(raw))
    return mon


def _run_stream_track_emits(stream: np.ndarray) -> tuple[AnalogConnectionMonitor, list[bool]]:
    """Run a stream, recording (state != DETERMINING and is_awake) per tick."""
    mon = AnalogConnectionMonitor()
    emits: list[bool] = []
    for raw in stream:
        mon.observe(int(raw))
        emits.append(mon.is_awake)
    return mon, emits


# ─── Startup classification ──────────────────────────────────────────


class TestStartupClassification:
    """The first WINDOW samples classify the channel as ASLEEP or AWAKE."""

    def test_floating_classified_asleep_high_rate(self):
        """≥95% of 16-sample floating windows → ASLEEP (measured: 96.1%)."""
        trials = 1000
        asleep_count = 0
        for i in range(trials):
            r = np.random.default_rng(1000 + i)
            stream = floating_stream(AnalogConnectionMonitor.WINDOW, r)
            mon = _run_stream(stream)
            if mon.state is AnalogConnectionState.ASLEEP:
                asleep_count += 1
        rate = asleep_count / trials
        assert rate >= 0.95, f"floating→ASLEEP rate {rate:.1%} < 95%"

    def test_connected_at_rest_never_asleep(self):
        """A connected pot at any parked position must NEVER be ASLEEP.

        This is the musical-instrument invariant: never silence a real
        pedal at startup. Tested across the full range of parked values
        including heel-down (0) and toe-down (1023).
        """
        trials = 1000
        for val in [0, 30, 100, 512, 1023]:
            asleep = 0
            for i in range(trials):
                r = np.random.default_rng(2000 + i + val)
                stream = connected_at_rest(AnalogConnectionMonitor.WINDOW, val, r)
                mon = _run_stream(stream)
                if mon.state is AnalogConnectionState.ASLEEP:
                    asleep += 1
            assert asleep == 0, f"connected@{val}: {asleep}/{trials} false ASLEEP"

    def test_connected_moving_fast_sweep_stays_awake(self):
        """A fast pedal sweep (>128 LSB over 160 ms) at startup must be AWAKE.

        std≈78, E≈256 — exceeds the upper bounds (50, 150), so correctly
        classified AWAKE. A slow sweep near heel (0→64, std≈20, E≈64)
        overlaps the floating band and may be ASLEEP, but the wake
        mechanism recovers it (tested in TestRuntimeWake).
        """
        trials = 1000
        for v0, v1 in [(0, 256), (256, 0), (0, 1023), (512, 800)]:
            asleep = 0
            for i in range(trials):
                r = np.random.default_rng(3000 + i)
                stream = connected_moving(AnalogConnectionMonitor.WINDOW, v0, v1, r)
                mon = _run_stream(stream)
                if mon.state is AnalogConnectionState.ASLEEP:
                    asleep += 1
            assert asleep == 0, f"moving {v0}->{v1}: {asleep}/{trials} false ASLEEP"

    def test_startup_takes_exactly_window_samples(self):
        """Classification happens after exactly WINDOW samples, not before."""
        mon = AnalogConnectionMonitor()
        for i in range(AnalogConnectionMonitor.WINDOW - 1):
            mon.observe(500)
            assert mon.state is AnalogConnectionState.DETERMINING
        mon.observe(500)
        assert mon.state is AnalogConnectionState.AWAKE


# ─── Runtime wake (plug-in) ──────────────────────────────────────────


class TestRuntimeWake:
    """An ASLEEP channel must wake promptly when a pedal is plugged in."""

    @pytest.mark.parametrize("plug_value", [100, 200, 400, 700])
    def test_wake_within_few_frames(self, plug_value):
        """Plug-in to a value ≥ 100 wakes within 2 frames (20 ms)."""
        rng = np.random.default_rng(7)
        stream = plugin_event(200, plug_value, rng)
        mon = AnalogConnectionMonitor()
        woke_at = None
        for i, raw in enumerate(stream):
            mon.observe(int(raw))
            if i >= 200 and mon.state is AnalogConnectionState.AWAKE:
                woke_at = i - 200
                break
        assert woke_at is not None, f"plug@{plug_value}: never woke"
        assert woke_at <= 2, f"plug@{plug_value}: woke after {woke_at} frames (>{2})"

    def test_wake_emits_immediately(self):
        """On wake, the current reading passes through (caller emits it)."""
        rng = np.random.default_rng(11)
        stream = plugin_event(100, 400, rng)
        mon, emits = _run_stream_track_emits(stream)
        # At the plug frame (idx 100), the monitor should be awake.
        assert emits[100] is True
        assert mon.state is AnalogConnectionState.AWAKE


# ─── Runtime sleep (unplug) ──────────────────────────────────────────


class TestRuntimeSleep:
    """An AWAKE channel must go ASLEEP when the pedal is unplugged."""

    @pytest.mark.parametrize("conn_value", [200, 512, 800])
    def test_sleep_within_window_after_unplug(self, conn_value):
        """After unplug, channel sleeps within WINDOW+16 frames (320 ms)."""
        rng = np.random.default_rng(11)
        stream = unplug_event(conn_value, 400, rng, n_float=500)
        mon = AnalogConnectionMonitor()
        slept_at = None
        for i, raw in enumerate(stream):
            mon.observe(int(raw))
            if i >= 400 and mon.state is AnalogConnectionState.ASLEEP:
                slept_at = i - 400
                break
        assert slept_at is not None, f"unplug@{conn_value}: never slept"
        limit = AnalogConnectionMonitor.WINDOW + 16
        assert slept_at <= limit, f"unplug@{conn_value}: slept after {slept_at} (>{limit})"

    def test_connected_at_rest_never_sleeps_at_runtime(self):
        """A connected, stationary pedal must not be put to sleep at runtime."""
        for val in [0, 30, 100, 512, 1023]:
            rng = np.random.default_rng(99 + val)
            stream = connected_at_rest(6000, val, rng)
            mon, emits = _run_stream_track_emits(stream)
            # After startup, should be AWAKE and stay AWAKE.
            assert mon.state is AnalogConnectionState.AWAKE, f"connected@{val} slept at runtime"
            # Every tick after startup should be awake.
            false_sleeps = sum(1 for e in emits[AnalogConnectionMonitor.WINDOW :] if not e)
            assert false_sleeps == 0, f"connected@{val}: {false_sleeps} false-sleep ticks"


# ─── Noise leakage while ASLEEP ──────────────────────────────────────


class TestNoiseLeakage:
    """A floating channel may briefly wake on noise — bounded leakage."""

    def test_floating_leakage_rate_bounded(self):
        """While floating for 60 s, ≤ 5% of ticks emit (false wakes accepted).

        The measured false-wake rate at threshold 48 LSB is ~1.2%; we
        allow 5% headroom for handling transitions the user accepts.
        """
        rng = np.random.default_rng(42)
        stream = floating_stream(6000, rng)
        mon = AnalogConnectionMonitor()
        awake_ticks = 0
        total_ticks = 0
        for raw in stream:
            mon.observe(int(raw))
            total_ticks += 1
            if mon.is_awake:
                awake_ticks += 1
        # Only count post-startup ticks.
        post = total_ticks - AnalogConnectionMonitor.WINDOW
        awake_post = awake_ticks - sum(1 for _ in range(AnalogConnectionMonitor.WINDOW))
        leak_rate = awake_post / post
        assert leak_rate <= 0.05, f"floating leakage {leak_rate:.1%} > 5%"


# ─── Baseline drift tracking ─────────────────────────────────────────


class TestBaselineDrift:
    """The EMA baseline must track slow floating drift to avoid false wakes."""

    def test_baseline_drifts_with_floating_mean(self):
        """Over a long floating stream, baseline follows the wandering mean."""
        rng = np.random.default_rng(55)
        stream = floating_stream(6000, rng)
        mon = AnalogConnectionMonitor()
        for raw in stream:
            mon.observe(int(raw))
        # After 6000 samples, baseline should be within the stream's
        # recent mean range (not stuck at the startup value).
        recent_mean = float(stream[-100:].mean())
        assert abs(mon.baseline - recent_mean) < 30, (
            f"baseline {mon.baseline:.1f} not tracking recent mean {recent_mean:.1f}"
        )


# ─── State machine properties ────────────────────────────────────────


class TestStateMachineProperties:
    """General invariants of the state machine."""

    def test_state_transitions_are_valid(self):
        """State only follows DETERMINING → {AWAKE, ASLEEP} → {AWAKE ⇄ ASLEEP}."""
        rng = np.random.default_rng(77)
        stream = plugin_event(200, 400, rng, n_post=200)
        stream = np.concatenate([stream, floating_stream(200, np.random.default_rng(78))])
        mon = AnalogConnectionMonitor()
        prev = AnalogConnectionState.DETERMINING
        for raw in stream:
            mon.observe(int(raw))
            cur = mon.state
            if prev is AnalogConnectionState.DETERMINING:
                assert cur in (
                    AnalogConnectionState.AWAKE,
                    AnalogConnectionState.ASLEEP,
                    AnalogConnectionState.DETERMINING,
                )
            else:
                assert cur in (AnalogConnectionState.AWAKE, AnalogConnectionState.ASLEEP)
            prev = cur

    def test_observe_never_raises_on_any_valid_adc(self):
        """Every value in [0, 1023] is accepted without error."""
        mon = AnalogConnectionMonitor()
        for v in [0, 1, 512, 1022, 1023]:
            mon.observe(v)
        assert mon.state is AnalogConnectionState.DETERMINING  # not enough samples yet


# ─── Measured-data validation (the real captured streams) ────────────


class TestMeasuredDataValidation:
    """Validate against actual ADC captures from pistomp@pistomp.local.

    These tests use the measured floating + connected streams captured
    on 2026-07-09 (60 Hz environment, v2 core). They are skipped if the
    .npy files are not present (e.g. CI without the captures).
    """

    SLOW_PATH = str(Path(__file__).parent / "fixtures" / "adc_slow.npy")

    @pytest.fixture
    def slow_data(self):
        pytest.importorskip("numpy")
        if not Path(self.SLOW_PATH).exists():
            pytest.skip(f"measured capture {self.SLOW_PATH} not available")
        return np.load(self.SLOW_PATH)

    def test_measured_connected_channel_stays_awake(self, slow_data):
        """CH0 (connected, σ≈0.4) must classify AWAKE and stay AWAKE."""
        ch0 = slow_data[:, 1].astype(int)  # CH0
        mon, emits = _run_stream_track_emits(ch0)
        assert mon.state is AnalogConnectionState.AWAKE
        # Never sleeps at runtime.
        false_sleeps = sum(1 for e in emits[AnalogConnectionMonitor.WINDOW :] if not e)
        assert false_sleeps == 0

    def test_measured_floating_channel_classifies_asleep(self, slow_data):
        """CH1 (floating, σ≈23) must classify ASLEEP at startup."""
        ch1 = slow_data[:, 2].astype(int)  # CH1
        mon = AnalogConnectionMonitor()
        for raw in ch1[: AnalogConnectionMonitor.WINDOW]:
            mon.observe(int(raw))
        assert mon.state is AnalogConnectionState.ASLEEP

    def test_measured_floating_leakage_bounded(self, slow_data):
        """CH1 floating for 60 s: ≤ 5% leakage (accepted false wakes)."""
        ch1 = slow_data[:, 2].astype(int)
        mon = AnalogConnectionMonitor()
        awake_post = 0
        for i, raw in enumerate(ch1):
            mon.observe(int(raw))
            if i >= AnalogConnectionMonitor.WINDOW and mon.is_awake:
                awake_post += 1
        post = len(ch1) - AnalogConnectionMonitor.WINDOW
        leak = awake_post / post
        assert leak <= 0.05, f"measured floating leakage {leak:.1%} > 5%"

    def test_measured_ch7_floating_classifies_asleep(self, slow_data):
        """CH7 (floating, sigma≈34 — worst channel) must reach ASLEEP.

        The first 16 samples may land at a beat peak (std > 50, exceeding
        the upper bound → AWAKE), but the rolling window recovers within
        ~3 s as the aliased beat subsides.
        """
        ch7 = slow_data[:, 3].astype(int)  # CH7
        mon = AnalogConnectionMonitor()
        for raw in ch7[:500]:
            mon.observe(int(raw))
            if mon.state is AnalogConnectionState.ASLEEP:
                return
        assert False, "CH7 never reached ASLEEP in 500 ticks (5 s)"
