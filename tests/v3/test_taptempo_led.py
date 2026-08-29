"""Taptempo footswitch LED — two metronome sources, one driver.

The taptempo footswitch's LED flashes from whichever beat source is active:
  - Transport anchored (beat_sync received): beat_grid drives the flash,
    white on downbeat, grey on beat.
  - Taptempo only (no beat_sync, but taptempo enabled with bpm): beat_grid
    runs free from taptempo.anchor + bpm — on for the first 50ms of each beat
    period, off otherwise. The free grid has beats but no bars.
  - Taptempo disabled: the footswitch behaves as a default toggle — no
    metronome flash, whether or not the transport is anchored.

The gpiozero hardware blink() is gone — the 10ms driver tick computes on/off
from the taptempo phase, same as it does for the transport-anchored case.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from modalapi.modhandler import _METRONOME_BEAT_RGB, _METRONOME_DOWNBEAT_RGB
from pistomp.beatsync import TickState
from tests.types import SystemFixture


def _find_taptempo_fs(v3_system: SystemFixture):
    for fs in v3_system.hw.footswitches:
        if fs.taptempo is not None:
            return fs
    raise AssertionError("No taptempo footswitch in v3 fixture")


def _mock_fs(fs):
    fs.pixel = MagicMock()
    fs.led = MagicMock()


def _enable_tap(fs):
    assert fs.taptempo is not None
    fs.taptempo.enable(True)


class TestTransportAnchored:
    """When beat_grid is anchored (beat_sync received) and tap tempo mode is on,
    the taptempo footswitch flashes beat-synced from the transport — same as the
    old _drive_metronome."""

    def test_flashing_beat_shows_beat_color(self, v3_system: SystemFixture):
        fs = _find_taptempo_fs(v3_system)
        _mock_fs(fs)
        _enable_tap(fs)
        beat = TickState(is_anchored=True, is_flashing=True, is_bar_start=False, bpm=120.0, bpb=4.0, beat_phase=0.0)
        v3_system.handler._drive_footswitch_leds(beat)
        fs.pixel.set_color.assert_called_once_with(_METRONOME_BEAT_RGB)
        fs.pixel.set_enable.assert_called_once_with(True)
        assert fs.led is not None
        fs.led.on.assert_called_once()  # type: ignore[unionAttr]

    def test_flashing_bar_start_shows_downbeat_color(self, v3_system: SystemFixture):
        fs = _find_taptempo_fs(v3_system)
        _mock_fs(fs)
        _enable_tap(fs)
        beat = TickState(is_anchored=True, is_flashing=True, is_bar_start=True, bpm=120.0, bpb=4.0, beat_phase=0.0)
        v3_system.handler._drive_footswitch_leds(beat)
        fs.pixel.set_color.assert_called_once_with(_METRONOME_DOWNBEAT_RGB)

    def test_not_flashing_turns_off(self, v3_system: SystemFixture):
        fs = _find_taptempo_fs(v3_system)
        _mock_fs(fs)
        _enable_tap(fs)
        beat = TickState(is_anchored=True, is_flashing=False, is_bar_start=False, bpm=120.0, bpb=4.0, beat_phase=0.5)
        v3_system.handler._drive_footswitch_leds(beat)
        fs.pixel.set_enable.assert_called_once_with(False)
        assert fs.led is not None
        fs.led.off.assert_called_once()  # type: ignore[unionAttr]


class TestTaptempoBlink:
    """When beat_grid is NOT anchored but taptempo is enabled with a bpm, the
    LED blinks from taptempo.anchor + bpm — computed by the 10ms driver, not
    gpiozero.blink()."""

    def test_taptempo_blink_on_within_flash_window(self, v3_system: SystemFixture):
        fs = _find_taptempo_fs(v3_system)
        _mock_fs(fs)
        assert fs.taptempo is not None
        fs.taptempo.enable(True)
        fs.taptempo.set_bpm(120.0)  # 120bpm → 500ms period, 50ms on-window
        fs.taptempo.anchor = 1000.0  # last tap at t=1000.0

        # Now=1000.025 → 25ms into the beat → within the 50ms on-window → ON
        with patch("modalapi.modhandler._now_us", return_value=int(1000.025 * 1_000_000)):
            v3_system.handler._drive_footswitch_leds()
        fs.pixel.set_enable.assert_called_once_with(True)
        assert fs.led is not None
        fs.led.on.assert_called_once()  # type: ignore[unionAttr]

    def test_taptempo_blink_off_outside_flash_window(self, v3_system: SystemFixture):
        fs = _find_taptempo_fs(v3_system)
        _mock_fs(fs)
        assert fs.taptempo is not None
        fs.taptempo.set_bpm(120.0)  # 500ms period, 50ms on-window
        fs.taptempo.anchor = 1000.0

        # Now=1000.3 → 300ms into the beat → past the 50ms on-window → OFF
        with patch("modalapi.modhandler._now_us", return_value=int(1000.3 * 1_000_000)):
            v3_system.handler._drive_footswitch_leds()
        fs.pixel.set_enable.assert_called_once_with(False)
        assert fs.led is not None
        fs.led.off.assert_called_once()  # type: ignore[unionAttr]

    def test_taptempo_zero_bpm_does_not_blink(self, v3_system: SystemFixture):
        """No taps yet (bpm=0) → no blink; fall through to default behavior."""
        fs = _find_taptempo_fs(v3_system)
        _mock_fs(fs)
        assert fs.taptempo is not None
        fs.taptempo.enable(True)
        fs.taptempo.set_bpm(0.0)
        v3_system.handler._drive_footswitch_leds()
        # No blink — the default behavior takes over (off when not toggled)
        fs.pixel.set_enable.assert_called_once_with(False)

    def test_taptempo_disabled_falls_through_to_default(self, v3_system: SystemFixture):
        """Taptempo disabled → the footswitch is a normal toggle; the driver
        renders from the default behavior (toggled + category color)."""
        fs = _find_taptempo_fs(v3_system)
        _mock_fs(fs)
        assert fs.taptempo is not None
        fs.taptempo.enable(False)
        fs.toggled = True
        v3_system.handler._drive_footswitch_leds()
        # Default behavior: toggled=True → pixel on with category color
        fs.pixel.set_enable.assert_called_once_with(True)

    def test_no_gpiozero_blink_called(self, v3_system: SystemFixture):
        """Regression: the gpiozero hardware blink() must not be called — the
        driver computes on/off from the taptempo phase at 10ms granularity."""
        fs = _find_taptempo_fs(v3_system)
        _mock_fs(fs)
        assert fs.taptempo is not None
        fs.taptempo.enable(True)
        fs.taptempo.set_bpm(120.0)
        fs.taptempo.anchor = 1000.0
        with patch("modalapi.modhandler._now_us", return_value=int(1000.05 * 1_000_000)):
            v3_system.handler._drive_footswitch_leds()
        assert fs.led is not None
        fs.led.blink.assert_not_called()  # type: ignore[unionAttr]


def test_anchored_transport_does_not_flash_when_disabled(v3_system: SystemFixture):
    """Transport anchored but tap tempo mode off → no metronome flash; the
    switch renders from its own binding like any other."""
    fs = _find_taptempo_fs(v3_system)
    _mock_fs(fs)
    assert fs.taptempo is not None
    fs.taptempo.enable(False)
    fs.toggled = True
    v3_system.handler._drive_footswitch_leds(
        TickState(is_anchored=True, is_flashing=False, is_bar_start=False, bpm=120.0, bpb=4.0, beat_phase=0.5)
    )
    fs.pixel.set_enable.assert_called_once_with(True)  # the flash would have blanked it


class TestLcdBorderSharesPhase:
    """The LCD tap border reads the same phase the LEDs flash on. It must not
    blink from taptempo.anchor while the transport is anchored."""

    def test_anchored_border_follows_beat_grid(self, v3_system: SystemFixture):
        fs = _find_taptempo_fs(v3_system)
        _mock_fs(fs)
        _enable_tap(fs)
        assert fs.taptempo is not None
        fs.taptempo.set_bpm(120.0)
        fs.taptempo.anchor = 1000.0  # a tap phase out of step with the grid

        with patch("modalapi.modhandler._now_us", return_value=int(1000.3 * 1_000_000)):
            v3_system.handler._drive_footswitch_leds(
                TickState(is_anchored=True, is_flashing=True, is_bar_start=False, bpm=120.0, bpb=4.0)
            )
            assert v3_system.handler.footswitch_tap_flash(fs) is True

            v3_system.handler._drive_footswitch_leds(
                TickState(is_anchored=True, is_flashing=False, is_bar_start=False, bpm=120.0, bpb=4.0, beat_phase=0.5)
            )
            assert v3_system.handler.footswitch_tap_flash(fs) is False

    def test_unanchored_border_follows_taptempo(self, v3_system: SystemFixture):
        fs = _find_taptempo_fs(v3_system)
        _mock_fs(fs)
        _enable_tap(fs)
        assert fs.taptempo is not None
        fs.taptempo.set_bpm(120.0)
        fs.taptempo.anchor = 1000.0

        with patch("modalapi.modhandler._now_us", return_value=int(1000.025 * 1_000_000)):
            v3_system.handler._drive_footswitch_leds()
            assert v3_system.handler.footswitch_tap_flash(fs) is True

        with patch("modalapi.modhandler._now_us", return_value=int(1000.3 * 1_000_000)):
            v3_system.handler._drive_footswitch_leds()
            assert v3_system.handler.footswitch_tap_flash(fs) is False

    def test_no_tempo_yet_stays_lit(self, v3_system: SystemFixture):
        fs = _find_taptempo_fs(v3_system)
        _mock_fs(fs)
        _enable_tap(fs)
        assert fs.taptempo is not None
        fs.taptempo.set_bpm(0.0)
        v3_system.handler._drive_footswitch_leds()
        assert v3_system.handler.footswitch_tap_flash(fs) is True


class TestBpmChangeReachesTheGrid:
    """A tweak knob or a tap changes the BPM through mod-ui's `transport`
    path. mod-host updates its globals but sends no clock sample, thus the
    grid learns the new rate only from `_adopt_bpm`. Without that, the LED
    keeps the old rate until the next bar heartbeat — up to 4s at 60 BPM."""

    def test_adopt_bpm_retunes_an_anchored_grid(self, v3_system: SystemFixture):
        v3_system.ws_bridge.inject("beat_sync 1000000000 120.0 4 0.0 1")
        v3_system.handler.poll_modui_changes()
        assert v3_system.handler.beat_grid.is_anchored is True

        v3_system.handler._adopt_bpm(60.0)

        with patch("modalapi.modhandler._now_us", return_value=1_000_000_000):
            beat = v3_system.handler.beat_grid.tick(1_000_000_000)
        assert beat.bpm == 60.0

    def test_adopt_bpm_keeps_the_beat_phase(self, v3_system: SystemFixture):
        v3_system.ws_bridge.inject("beat_sync 1000000000 120.0 4 0.0 1")
        v3_system.handler.poll_modui_changes()

        grid = v3_system.handler.beat_grid
        half_beat_us = 1_000_000_000 + 250_000
        assert grid.tick(half_beat_us).beat_phase == pytest.approx(0.5)

        with patch("modalapi.modhandler._now_us", return_value=half_beat_us):
            v3_system.handler._adopt_bpm(60.0)
        assert grid.tick(half_beat_us).beat_phase == pytest.approx(0.5)
