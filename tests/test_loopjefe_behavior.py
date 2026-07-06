"""LoopJefe footswitch behavior — state→color/style contract + registration.

Pins:
  - The loopjefe URIs are registered (plugins/__init__.py imports plugins.loopjefe).
  - make_loopjefe_behavior produces a behavior with momentary=True and the
    expected output_subscriptions.
  - led_color / led_style for all 9 states, including the measure_number==0
    loop-downbeat tint.
  - Brightness/pulse is the driver's job — not tested here.
"""

from __future__ import annotations

import pytest

from modalapi.footswitch_behavior import LedDisplayStyle
from modalapi.plugin import Plugin
from pistomp.beatsync import TickState
from plugins import lookup, registered_uris
from plugins.loopjefe import LOOPJEFE_URIS, make_loopjefe_behavior


def _tick(beat_phase: float = 0.0, is_bar_start: bool = False) -> TickState:
    return TickState(
        is_anchored=True,
        is_flashing=is_bar_start,
        is_bar_start=is_bar_start,
        bpm=120.0,
        bpb=4.0,
        beat_phase=beat_phase,
    )


def _make_plugin(uri: str = LOOPJEFE_URIS[0]) -> Plugin:
    customization = lookup(uri)
    # Plugin() requires a parameters dict; loopjefe behavior only reads instance_id.
    return Plugin("loopjefe", {}, {}, "Looper", uri=uri, customization=customization)


class TestRegistration:
    def test_loopjefe_uris_are_registered(self):
        registered = registered_uris()
        for uri in LOOPJEFE_URIS:
            assert uri in registered, f"{uri} not registered — plugins/__init__.py must import plugins.loopjefe"

    def test_lookup_returns_loopjefe_customization_with_behavior_fn(self):
        for uri in LOOPJEFE_URIS:
            cust = lookup(uri)
            assert cust.footswitch_behavior_fn is make_loopjefe_behavior, (
                f"lookup({uri!r}) did not return the loopjefe customization"
            )


class TestBehaviorContract:
    def test_momentary_short_press(self):
        b = make_loopjefe_behavior(_make_plugin())
        assert b.momentary is True

    def test_output_subscriptions_state_and_measure_number(self):
        b = make_loopjefe_behavior(_make_plugin())
        assert set(b.output_subscriptions()) == {"state", "measure_number"}

    def test_on_output_caches_state(self):
        b = make_loopjefe_behavior(_make_plugin())
        b.on_output("state", 2.0)
        b.on_output("measure_number", 1.0)  # non-downbeat so base color is returned
        assert b.led_color(_tick()) == (255, 0, 0)  # Recording

    def test_on_output_caches_measure_number(self):
        b = make_loopjefe_behavior(_make_plugin())
        b.on_output("state", 1.0)  # Record Arm → blue
        b.on_output("measure_number", 0.0)
        # measure_number == 0 → downbeat tint (brighter)
        assert b.led_color(_tick()) != (0, 80, 255)
        b.on_output("measure_number", 3.0)
        assert b.led_color(_tick()) == (0, 80, 255)


class TestStateColorAndStyle:
    @pytest.mark.parametrize("state,expected_color", [
        (0, None),              # Empty → off
        (1, (0, 80, 255)),      # Record Arm → blue
        (2, (255, 0, 0)),       # Recording → red
        (3, (0, 80, 255)),      # Record Close → blue
        (4, (0, 255, 0)),       # Playback → green
        (5, (80, 80, 80)),      # Stopped → steady grey
        (6, (0, 80, 255)),      # Overdub Arm → blue
        (7, (255, 140, 0)),     # Overdub → orange
        (8, (0, 80, 255)),      # Overdub Close → blue
    ])
    def test_state_color_with_nonzero_measure(self, state, expected_color):
        b = make_loopjefe_behavior(_make_plugin())
        b.on_output("state", float(state))
        b.on_output("measure_number", 1.0)  # not the loop downbeat
        assert b.led_color(_tick()) == expected_color

    @pytest.mark.parametrize("state,expected_style", [
        (0, LedDisplayStyle.SOLID),       # Empty → off, solid
        (5, LedDisplayStyle.SOLID),       # Stopped → steady grey
        (1, LedDisplayStyle.METRONOME),   # active → pulse
        (2, LedDisplayStyle.METRONOME),
        (3, LedDisplayStyle.METRONOME),
        (4, LedDisplayStyle.METRONOME),
        (6, LedDisplayStyle.METRONOME),
        (7, LedDisplayStyle.METRONOME),
        (8, LedDisplayStyle.METRONOME),
    ])
    def test_state_style(self, state, expected_style):
        b = make_loopjefe_behavior(_make_plugin())
        b.on_output("state", float(state))
        assert b.led_style(_tick()) == expected_style


class TestLoopDownbeatTint:
    def test_measure_zero_returns_distinct_color(self):
        b = make_loopjefe_behavior(_make_plugin())
        b.on_output("state", 2.0)  # Recording → red
        b.on_output("measure_number", 0.0)
        downbeat = b.led_color(_tick())
        b.on_output("measure_number", 2.0)
        normal = b.led_color(_tick())
        assert downbeat is not None and normal is not None
        assert downbeat != normal
        # The downbeat tint brightens each channel that wasn't already at 255
        assert all(d >= n for d, n in zip(downbeat, normal))
        assert any(d > n for d, n in zip(downbeat, normal))

    def test_measure_zero_empty_state_still_off(self):
        b = make_loopjefe_behavior(_make_plugin())
        b.on_output("state", 0.0)
        b.on_output("measure_number", 0.0)
        assert b.led_color(_tick()) is None