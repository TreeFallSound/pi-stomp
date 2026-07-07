"""LoopJefe footswitch LED spec — state->color/style contract + registration.

Pins:
  - The loopjefe URIs are registered (plugins/__init__.py imports plugins.loopjefe).
  - The registered LedSpec renders all 9 states correctly via the generic
    render_led_spec driver, including the measure_number==0 loop-downbeat tint.
  - Momentary press semantics come from the port (pprops:trigger on
    advance/reset), not from anything here — not tested in this file.
  - Brightness/pulse envelope is the driver's job — not tested here.
"""

from __future__ import annotations

import pytest

from modalapi.led_render import LedDisplayStyle, render_led_spec
from modalapi.plugin_customization import LedSpec
from plugins import lookup, registered_uris
from plugins.loopjefe import LOOPJEFE_URIS


def _spec() -> LedSpec:
    spec = lookup(LOOPJEFE_URIS[0]).led_spec
    assert spec is not None
    return spec


class TestRegistration:
    def test_loopjefe_uris_are_registered(self):
        registered = registered_uris()
        for uri in LOOPJEFE_URIS:
            assert uri in registered, f"{uri} not registered — plugins/__init__.py must import plugins.loopjefe"

    def test_lookup_returns_loopjefe_led_spec(self):
        for uri in LOOPJEFE_URIS:
            cust = lookup(uri)
            assert cust.led_spec is not None, f"lookup({uri!r}) did not return the loopjefe LedSpec"
            assert cust.led_spec.state_symbol == "state"
            assert cust.led_spec.downbeat_symbol == "measure_number"


class TestStateColorAndStyle:
    @pytest.mark.parametrize("state,expected_color", [
        (0, None),              # Empty -> off
        (1, (0, 80, 255)),      # Record Arm -> blue
        (2, (255, 0, 0)),       # Recording -> red
        (3, (0, 80, 255)),      # Record Close -> blue
        (4, (0, 255, 0)),       # Playback -> green
        (5, (80, 80, 80)),      # Stopped -> steady grey
        (6, (0, 80, 255)),      # Overdub Arm -> blue
        (7, (255, 140, 0)),     # Overdub -> orange
        (8, (0, 80, 255)),      # Overdub Close -> blue
    ])
    def test_state_color_with_nonzero_measure(self, state, expected_color):
        color, _style = render_led_spec(_spec(), {"state": float(state), "measure_number": 1.0})
        assert color == expected_color

    @pytest.mark.parametrize("state,expected_style", [
        (0, LedDisplayStyle.SOLID),       # Empty -> off, solid
        (5, LedDisplayStyle.SOLID),       # Stopped -> steady grey
        (1, LedDisplayStyle.METRONOME),   # active -> pulse
        (2, LedDisplayStyle.METRONOME),
        (3, LedDisplayStyle.METRONOME),
        (4, LedDisplayStyle.METRONOME),
        (6, LedDisplayStyle.METRONOME),
        (7, LedDisplayStyle.METRONOME),
        (8, LedDisplayStyle.METRONOME),
    ])
    def test_state_style(self, state, expected_style):
        _color, style = render_led_spec(_spec(), {"state": float(state), "measure_number": 1.0})
        assert style == expected_style


class TestLoopDownbeatTint:
    def test_measure_zero_returns_distinct_color(self):
        downbeat, _ = render_led_spec(_spec(), {"state": 2.0, "measure_number": 0.0})  # Recording -> red
        normal, _ = render_led_spec(_spec(), {"state": 2.0, "measure_number": 2.0})
        assert downbeat is not None and normal is not None
        assert downbeat != normal
        # The downbeat tint brightens each channel that wasn't already at 255
        assert all(d >= n for d, n in zip(downbeat, normal))
        assert any(d > n for d, n in zip(downbeat, normal))

    def test_measure_zero_empty_state_still_off(self):
        color, _style = render_led_spec(_spec(), {"state": 0.0, "measure_number": 0.0})
        assert color is None
