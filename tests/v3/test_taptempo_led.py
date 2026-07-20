"""Taptempo footswitch LED — two metronome sources, one driver.

The taptempo footswitch's LED flashes from whichever beat source is active:
  - Transport anchored (beat_sync received): beat_grid drives the flash,
    white on downbeat, grey on beat.
  - Taptempo only (no beat_sync, but taptempo enabled with bpm): the LED
    blinks from taptempo.anchor + bpm — on for the first ~100ms of each
    beat period, off otherwise.
  - Taptempo disabled: the footswitch behaves as a default toggle.

The gpiozero hardware blink() is gone — the 10ms driver tick computes on/off
from the taptempo phase, same as it does for the transport-anchored case.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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


class TestTransportAnchored:
    """When beat_grid is anchored (beat_sync received), the taptempo footswitch
    flashes beat-synced from the transport — same as the old _drive_metronome."""

    def test_flashing_beat_shows_beat_color(self, v3_system: SystemFixture):
        fs = _find_taptempo_fs(v3_system)
        _mock_fs(fs)
        beat = TickState(is_anchored=True, is_flashing=True, is_bar_start=False,
                         bpm=120.0, bpb=4.0, beat_phase=0.0)
        v3_system.handler._drive_footswitch_leds(beat)
        fs.pixel.set_color.assert_called_once_with(_METRONOME_BEAT_RGB)
        fs.pixel.set_enable.assert_called_once_with(True)
        assert fs.led is not None
        fs.led.on.assert_called_once()  # type: ignore[unionAttr]

    def test_flashing_bar_start_shows_downbeat_color(self, v3_system: SystemFixture):
        fs = _find_taptempo_fs(v3_system)
        _mock_fs(fs)
        beat = TickState(is_anchored=True, is_flashing=True, is_bar_start=True,
                         bpm=120.0, bpb=4.0, beat_phase=0.0)
        v3_system.handler._drive_footswitch_leds(beat)
        fs.pixel.set_color.assert_called_once_with(_METRONOME_DOWNBEAT_RGB)

    def test_not_flashing_turns_off(self, v3_system: SystemFixture):
        fs = _find_taptempo_fs(v3_system)
        _mock_fs(fs)
        beat = TickState(is_anchored=True, is_flashing=False, is_bar_start=False,
                         bpm=120.0, bpb=4.0, beat_phase=0.5)
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
        fs.taptempo.set_bpm(120.0)  # 120bpm → 500ms period, 100ms on-window
        fs.taptempo.anchor = 1000.0  # last tap at t=1000.0

        # Now=1000.05 → 50ms into the beat → within the 100ms on-window → ON
        with patch("modalapi.modhandler._now_us", return_value=int(1000.05 * 1_000_000)):
            v3_system.handler._drive_footswitch_leds(
                TickState(is_anchored=False, is_flashing=False, is_bar_start=False,
                          bpm=120.0, bpb=4.0, beat_phase=0.0)
            )
        fs.pixel.set_enable.assert_called_once_with(True)
        assert fs.led is not None
        fs.led.on.assert_called_once()  # type: ignore[unionAttr]

    def test_taptempo_blink_off_outside_flash_window(self, v3_system: SystemFixture):
        fs = _find_taptempo_fs(v3_system)
        _mock_fs(fs)
        assert fs.taptempo is not None
        fs.taptempo.enable(True)
        fs.taptempo.set_bpm(120.0)  # 500ms period, 100ms on-window
        fs.taptempo.anchor = 1000.0

        # Now=1000.3 → 300ms into the beat → past the 100ms on-window → OFF
        with patch("modalapi.modhandler._now_us", return_value=int(1000.3 * 1_000_000)):
            v3_system.handler._drive_footswitch_leds(
                TickState(is_anchored=False, is_flashing=False, is_bar_start=False,
                          bpm=120.0, bpb=4.0, beat_phase=0.0)
            )
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
        v3_system.handler._drive_footswitch_leds(
            TickState(is_anchored=False, is_flashing=False, is_bar_start=False,
                      bpm=0.0, bpb=4.0, beat_phase=0.0)
        )
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
        v3_system.handler._drive_footswitch_leds(
            TickState(is_anchored=False, is_flashing=False, is_bar_start=False,
                      bpm=0.0, bpb=4.0, beat_phase=0.0)
        )
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
            v3_system.handler._drive_footswitch_leds(
                TickState(is_anchored=False, is_flashing=False, is_bar_start=False,
                          bpm=120.0, bpb=4.0, beat_phase=0.0)
            )
        assert fs.led is not None
        fs.led.blink.assert_not_called()  # type: ignore[unionAttr]