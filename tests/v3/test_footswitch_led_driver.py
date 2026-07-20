"""Unified footswitch LED driver — single source of truth for pixel + GPIO LED.

The driver runs in poll_controls (10ms, same tick as the press) so there's no
latency between a state change and the LED reflecting it. Both fs.pixel and
fs.led are written from the same (color, style) frame in the same driver call
— no separate set_led path.

Covers:
  - SOLID: shows the frame's color steadily (or off when color is None).
  - METRONOME: scales brightness by beat_phase (bright at 0, dim toward 1).
  - Unanchored METRONOME: steady color (no pulse).
  - Off: color is None -> pixel disabled, GPIO LED off.
  - Press renders in the same tick (poll_controls, not poll_indicators).
  - set_led is a pure state update -- no hardware writes.
  - Default per-footswitch renderer (no bound plugin / no LedSpec): toggle +
    category color, falling back to off when not toggled.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from modalapi.led_render import LedDisplayStyle
from modalapi.modhandler import Modhandler
from pistomp.beatsync import TickState
from pistomp.footswitch import Footswitch
from tests.types import SystemFixture


def _beat(beat_phase: float = 0.0, *, is_anchored: bool = True,
          is_bar_start: bool = False, is_flashing: bool | None = None) -> TickState:
    if is_flashing is None:
        is_flashing = is_bar_start
    return TickState(
        is_anchored=is_anchored,
        is_flashing=is_flashing,
        is_bar_start=is_bar_start,
        bpm=120.0,
        bpb=4.0,
        beat_phase=beat_phase,
    )


def _drive(handler: Modhandler, beat: TickState) -> None:
    """Invoke the driver directly with a fabricated beat state."""
    handler._drive_footswitch_leds(beat)


def _fs_with_frame(v3_system: SystemFixture, color, style: LedDisplayStyle = LedDisplayStyle.SOLID) -> Footswitch:
    """Stub the default per-footswitch renderer to return a fixed frame,
    bypassing plugin-binding lookup entirely — isolates the writer/envelope
    behavior under test from LedSpec rendering (covered in
    tests/test_loopjefe_behavior.py)."""
    fs = v3_system.hw.footswitches[0]
    v3_system.handler._render_footswitch = MagicMock(return_value=(color, style))  # type: ignore[method-assign]
    fs.pixel = MagicMock()
    fs.led = MagicMock()
    return fs


class TestSolidStyle:
    def test_solid_shows_color_steadily(self, v3_system: SystemFixture):
        fs = _fs_with_frame(v3_system, (0, 255, 0), LedDisplayStyle.SOLID)
        _drive(v3_system.handler, _beat(beat_phase=0.0))
        fs.pixel.set_color.assert_called_once_with((0, 255, 0))
        fs.pixel.set_enable.assert_called_once_with(True)
        assert fs.led is not None
        fs.led.on.assert_called_once()  # type: ignore[unionAttr]

    def test_solid_brightness_does_not_scale_with_phase(self, v3_system: SystemFixture):
        fs = _fs_with_frame(v3_system, (100, 100, 100), LedDisplayStyle.SOLID)
        _drive(v3_system.handler, _beat(beat_phase=0.9))
        # SOLID must not scale — full color at any phase
        fs.pixel.set_color.assert_called_once_with((100, 100, 100))

    def test_solid_none_color_disables_pixel_and_led(self, v3_system: SystemFixture):
        fs = _fs_with_frame(v3_system, None, LedDisplayStyle.SOLID)
        _drive(v3_system.handler, _beat())
        fs.pixel.set_enable.assert_called_once_with(False)
        assert fs.led is not None
        fs.led.off.assert_called_once()  # type: ignore[unionAttr]


class TestMetronomeStyle:
    def test_metronome_bright_at_phase_zero(self, v3_system: SystemFixture):
        fs = _fs_with_frame(v3_system, (100, 100, 100), LedDisplayStyle.METRONOME)
        _drive(v3_system.handler, _beat(beat_phase=0.0))
        # phase 0 → brightness 1.0 → unscaled color
        fs.pixel.set_color.assert_called_once_with((100, 100, 100))

    def test_metronome_dim_near_phase_one(self, v3_system: SystemFixture):
        fs = _fs_with_frame(v3_system, (100, 100, 100), LedDisplayStyle.METRONOME)
        _drive(v3_system.handler, _beat(beat_phase=0.9))
        scaled = fs.pixel.set_color.call_args.args[0]
        # phase 0.9 → brightness 1.0 - 0.9*0.7 = 0.37 → 100*0.37 = 37
        assert scaled == (37, 37, 37)
        assert all(c < 100 for c in scaled)

    def test_metronome_brightest_on_bar_start(self, v3_system: SystemFixture):
        fs = _fs_with_frame(v3_system, (100, 100, 100), LedDisplayStyle.METRONOME)
        _drive(v3_system.handler, _beat(beat_phase=0.5, is_bar_start=True))
        # bar start forces brightness 1.0 even though phase is mid-beat
        fs.pixel.set_color.assert_called_once_with((100, 100, 100))

    def test_metronome_unanchored_shows_steady_color(self, v3_system: SystemFixture):
        fs = _fs_with_frame(v3_system, (100, 100, 100), LedDisplayStyle.METRONOME)
        _drive(v3_system.handler, _beat(beat_phase=0.9, is_anchored=False))
        # No pulse when unanchored — full color
        fs.pixel.set_color.assert_called_once_with((100, 100, 100))


class TestDefaultRendering:
    """No bound plugin (or a bound plugin with no LedSpec) falls back to the
    built-in toggle + category-color renderer."""

    def test_unbound_untoggled_footswitch_is_off(self, v3_system: SystemFixture):
        fs = v3_system.hw.footswitches[0]
        fs.parameter = None
        fs.toggled = False
        fs.pixel = MagicMock()
        fs.led = MagicMock()
        _drive(v3_system.handler, _beat())
        fs.pixel.set_enable.assert_called_once_with(False)
        assert fs.led is not None
        fs.led.off.assert_called_once()  # type: ignore[unionAttr]

    def test_unbound_toggled_footswitch_shows_category_or_white(self, v3_system: SystemFixture):
        fs = v3_system.hw.footswitches[0]
        fs.parameter = None
        fs.toggled = True
        fs.category = None
        fs.pixel = MagicMock()
        fs.led = MagicMock()
        _drive(v3_system.handler, _beat())
        fs.pixel.set_color.assert_called_once_with((255, 255, 255))
        fs.pixel.set_enable.assert_called_once_with(True)


class TestPixelAndLedSameSource:
    """Both fs.pixel and fs.led are written from the same renderer query in the
    same driver call — no separate set_led path fighting the driver."""

    def test_solid_on_lights_both_pixel_and_led(self, v3_system: SystemFixture):
        fs = _fs_with_frame(v3_system, (0, 255, 0), LedDisplayStyle.SOLID)
        _drive(v3_system.handler, _beat())
        fs.pixel.set_enable.assert_called_once_with(True)
        assert fs.led is not None
        fs.led.on.assert_called_once()  # type: ignore[unionAttr]

    def test_off_disables_both_pixel_and_led(self, v3_system: SystemFixture):
        fs = _fs_with_frame(v3_system, None, LedDisplayStyle.SOLID)
        _drive(v3_system.handler, _beat())
        fs.pixel.set_enable.assert_called_once_with(False)
        assert fs.led is not None
        fs.led.off.assert_called_once()  # type: ignore[unionAttr]

    def test_set_led_does_not_touch_hardware(self, v3_system: SystemFixture):
        """set_led is a pure state update — it flips fs.toggled only. The next
        driver tick renders the new state to both pixel and LED."""
        fs = v3_system.hw.footswitches[0]
        fs.pixel = MagicMock()
        fs.led = MagicMock()
        fs.set_led(True)
        assert fs.toggled is True
        fs.pixel.set_enable.assert_not_called()
        fs.pixel.set_color.assert_not_called()
        assert fs.led is not None
        fs.led.on.assert_not_called()  # type: ignore[unionAttr]
        fs.led.off.assert_not_called()  # type: ignore[unionAttr]
        fs.led.blink.assert_not_called()  # type: ignore[unionAttr]


class TestDriverRunsInPollControls:
    """The LED driver runs in poll_controls (10ms), not poll_indicators (20ms),
    so a press and its LED update happen in the same tick."""

    def test_poll_controls_drives_leds(self, v3_system: SystemFixture):
        fs = _fs_with_frame(v3_system, (0, 255, 0), LedDisplayStyle.SOLID)
        with patch.object(v3_system.hw, "poll_controls"):
            v3_system.handler.poll_controls()
        fs.pixel.set_color.assert_called_once_with((0, 255, 0))
        fs.pixel.set_enable.assert_called_once_with(True)

    def test_poll_indicators_does_not_drive_footswitch_leds(self, v3_system: SystemFixture):
        """poll_indicators still drives hardware.indicators (VU meters) but no
        longer drives footswitch LEDs — that moved to poll_controls."""
        fs = _fs_with_frame(v3_system, (0, 255, 0), LedDisplayStyle.SOLID)
        with patch.object(v3_system.hw, "poll_indicators"):
            v3_system.handler.poll_indicators()
        fs.pixel.set_color.assert_not_called()
        fs.pixel.set_enable.assert_not_called()
