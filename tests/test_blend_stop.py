"""Unit tests for blend/stop.py — segment diff-map builder."""

import pytest

from blend.stop import BlendStop, build_segment_diff_map
from modalapi.parameter import Type as ParameterType


# ---------------------------------------------------------------------------
# Binary "on wins" semantics
# ---------------------------------------------------------------------------


def _type_getter(type_for: dict[tuple[str, str], ParameterType]):
    return lambda instance_id, symbol: type_for.get((instance_id, symbol), ParameterType.DEFAULT)


def test_toggled_param_collapses_to_on_when_either_side_is_on():
    lower = BlendStop(0.0, 0, {"Fx": {"Switch": 0.0}})
    upper = BlendStop(1.0, 1, {"Fx": {"Switch": 1.0}})
    getter = _type_getter({("Fx", "Switch"): ParameterType.TOGGLED})

    result = build_segment_diff_map(lower, upper, getter)
    pd = result["Fx"]["Switch"]
    assert pd.val_a == pytest.approx(1.0)
    assert pd.val_b == pytest.approx(1.0)


def test_bypass_symbol_collapses_to_on_regardless_of_type():
    lower = BlendStop(0.0, 0, {"Fx": {":bypass": 1.0}})
    upper = BlendStop(1.0, 1, {"Fx": {":bypass": 0.0}})

    result = build_segment_diff_map(lower, upper, _type_getter({}))
    pd = result["Fx"][":bypass"]
    assert pd.val_a == pytest.approx(1.0)
    assert pd.val_b == pytest.approx(1.0)


def test_default_continuous_param_keeps_both_endpoints():
    lower = BlendStop(0.0, 0, {"Fx": {"Vol": 0.2}})
    upper = BlendStop(1.0, 1, {"Fx": {"Vol": 0.8}})

    result = build_segment_diff_map(lower, upper, _type_getter({}))
    pd = result["Fx"]["Vol"]
    assert pd.val_a == pytest.approx(0.2)
    assert pd.val_b == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# MIDI-bound exclusion
# ---------------------------------------------------------------------------


def test_midi_bound_param_is_excluded():
    lower = BlendStop(0.0, 0, {"Fx": {"Vol": 0.0, "Bound": 0.0}})
    upper = BlendStop(1.0, 1, {"Fx": {"Vol": 1.0, "Bound": 1.0}})
    result = build_segment_diff_map(lower, upper, _type_getter({}), {("Fx", "Bound")})
    assert "Vol" in result.get("Fx", {})
    assert "Bound" not in result.get("Fx", {})


def test_instance_dropped_when_all_its_params_are_excluded():
    lower = BlendStop(0.0, 0, {"Fx": {"Bound": 0.0}})
    upper = BlendStop(1.0, 1, {"Fx": {"Bound": 1.0}})
    result = build_segment_diff_map(lower, upper, _type_getter({}), {("Fx", "Bound")})
    assert "Fx" not in result


def test_equal_value_params_are_dropped():
    lower = BlendStop(0.0, 0, {"Fx": {"Same": 0.5}})
    upper = BlendStop(1.0, 1, {"Fx": {"Same": 0.5}})
    result = build_segment_diff_map(lower, upper, _type_getter({}))
    assert result == {}
