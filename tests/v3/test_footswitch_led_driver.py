"""Unified footswitch LED driver — single source of truth for pixel + GPIO LED.

The driver runs in poll_controls (10ms, same tick as the press) so there's no
latency between a state change and the LED reflecting it. Both fs.pixel and
fs.led are written from the same behavior query — no separate set_led path.

Covers:
  - SOLID: shows the behavior's color steadily (or off when color is None).
  - METRONOME: scales brightness by beat_phase (bright at 0, dim toward 1).
  - Unanchored METRONOME: steady color (no pulse).
  - Off: color is None → pixel disabled, GPIO LED off.
  - Press renders in the same tick (poll_controls, not poll_indicators).
  - set_led is a pure state update — no hardware writes.
  - Taptempo footswitch: transport-anchored → beat-synced flash; taptempo-only
    → blink from taptempo.anchor + bpm; taptempo disabled → default behavior.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from modalapi.footswitch_behavior import LedDisplayStyle
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


class _StubBehavior:
    """Minimal behavior stub for driver tests — returns a fixed color/style."""

    def __init__(self, color, style: LedDisplayStyle = LedDisplayStyle.SOLID,
                 momentary: bool = False) -> None:
        self._color = color
        self._style = style
        self.momentary = momentary

    def output_subscriptions(self):
        return ()

    def on_output(self, symbol: str, value: float) -> None:
        pass

    def led_color(self, beat: TickState):
        return self._color

    def led_style(self, beat: TickState) -> LedDisplayStyle:
        return self._style


def _drive(handler: Modhandler, beat: TickState) -> None:
    """Invoke the driver directly with a fabricated beat state."""
    handler._drive_footswitch_leds(beat)


def _fs_with_behavior(v3_system: SystemFixture, behavior) -> Footswitch:
    fs = v3_system.hw.footswitches[0]
    fs.behavior = behavior
    fs.pixel = MagicMock()
    fs.led = MagicMock()
    return fs


class TestSolidStyle:
    def test_solid_shows_color_steadily(self, v3_system: SystemFixture):
        fs = _fs_with_behavior(v3_system, _StubBehavior((0, 255, 0), LedDisplayStyle.SOLID))
        _drive(v3_system.handler, _beat(beat_phase=0.0))
        fs.pixel.set_color.assert_called_once_with((0, 255, 0))
        fs.pixel.set_enable.assert_called_once_with(True)
        assert fs.led is not None
        fs.led.on.assert_called_once()  # type: ignore[unionAttr]

    def test_solid_brightness_does_not_scale_with_phase(self, v3_system: SystemFixture):
        fs = _fs_with_behavior(v3_system, _StubBehavior((100, 100, 100), LedDisplayStyle.SOLID))
        _drive(v3_system.handler, _beat(beat_phase=0.9))
        # SOLID must not scale — full color at any phase
        fs.pixel.set_color.assert_called_once_with((100, 100, 100))

    def test_solid_none_color_disables_pixel_and_led(self, v3_system: SystemFixture):
        fs = _fs_with_behavior(v3_system, _StubBehavior(None, LedDisplayStyle.SOLID))
        _drive(v3_system.handler, _beat())
        fs.pixel.set_enable.assert_called_once_with(False)
        assert fs.led is not None
        fs.led.off.assert_called_once()  # type: ignore[unionAttr]


class TestMetronomeStyle:
    def test_metronome_bright_at_phase_zero(self, v3_system: SystemFixture):
        fs = _fs_with_behavior(v3_system, _StubBehavior((100, 100, 100), LedDisplayStyle.METRONOME))
        _drive(v3_system.handler, _beat(beat_phase=0.0))
        # phase 0 → brightness 1.0 → unscaled color
        fs.pixel.set_color.assert_called_once_with((100, 100, 100))

    def test_metronome_dim_near_phase_one(self, v3_system: SystemFixture):
        fs = _fs_with_behavior(v3_system, _StubBehavior((100, 100, 100), LedDisplayStyle.METRONOME))
        _drive(v3_system.handler, _beat(beat_phase=0.9))
        scaled = fs.pixel.set_color.call_args.args[0]
        # phase 0.9 → brightness 1.0 - 0.9*0.7 = 0.37 → 100*0.37 = 37
        assert scaled == (37, 37, 37)
        assert all(c < 100 for c in scaled)

    def test_metronome_brightest_on_bar_start(self, v3_system: SystemFixture):
        fs = _fs_with_behavior(v3_system, _StubBehavior((100, 100, 100), LedDisplayStyle.METRONOME))
        _drive(v3_system.handler, _beat(beat_phase=0.5, is_bar_start=True))
        # bar start forces brightness 1.0 even though phase is mid-beat
        fs.pixel.set_color.assert_called_once_with((100, 100, 100))

    def test_metronome_unanchored_shows_steady_color(self, v3_system: SystemFixture):
        fs = _fs_with_behavior(v3_system, _StubBehavior((100, 100, 100), LedDisplayStyle.METRONOME))
        _drive(v3_system.handler, _beat(beat_phase=0.9, is_anchored=False))
        # No pulse when unanchored — full color
        fs.pixel.set_color.assert_called_once_with((100, 100, 100))


class TestNoBehavior:
    def test_footswitch_without_behavior_is_skipped(self, v3_system: SystemFixture):
        fs = v3_system.hw.footswitches[0]
        fs.behavior = None
        fs.pixel = MagicMock()
        _drive(v3_system.handler, _beat())
        fs.pixel.set_enable.assert_not_called()
        fs.pixel.set_color.assert_not_called()


class TestPixelAndLedSameSource:
    """Both fs.pixel and fs.led are written from the same behavior query in the
    same driver call — no separate set_led path fighting the driver."""

    def test_solid_on_lights_both_pixel_and_led(self, v3_system: SystemFixture):
        fs = _fs_with_behavior(v3_system, _StubBehavior((0, 255, 0), LedDisplayStyle.SOLID))
        _drive(v3_system.handler, _beat())
        fs.pixel.set_enable.assert_called_once_with(True)
        assert fs.led is not None
        fs.led.on.assert_called_once()  # type: ignore[unionAttr]

    def test_off_disables_both_pixel_and_led(self, v3_system: SystemFixture):
        fs = _fs_with_behavior(v3_system, _StubBehavior(None, LedDisplayStyle.SOLID))
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
        fs = _fs_with_behavior(v3_system, _StubBehavior((0, 255, 0), LedDisplayStyle.SOLID))
        with patch.object(v3_system.hw, "poll_controls"):
            v3_system.handler.poll_controls()
        fs.pixel.set_color.assert_called_once_with((0, 255, 0))
        fs.pixel.set_enable.assert_called_once_with(True)

    def test_poll_indicators_does_not_drive_footswitch_leds(self, v3_system: SystemFixture):
        """poll_indicators still drives hardware.indicators (VU meters) but no
        longer drives footswitch LEDs — that moved to poll_controls."""
        fs = _fs_with_behavior(v3_system, _StubBehavior((0, 255, 0), LedDisplayStyle.SOLID))
        with patch.object(v3_system.hw, "poll_indicators"):
            v3_system.handler.poll_indicators()
        fs.pixel.set_color.assert_not_called()
        fs.pixel.set_enable.assert_not_called()