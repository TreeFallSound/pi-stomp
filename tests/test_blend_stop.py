"""Unit tests for blend/stop.py — BlendStop methods."""

import pytest

from blend.stop import BlendStop
from modalapi.parameter import Type as ParameterType


# ---------------------------------------------------------------------------
# adjust_binary_params
# ---------------------------------------------------------------------------


def test_adjust_binary_params_toggled_type_on_wins():
    diff_map = {"/Fx": {"Switch": (0.0, 1.0, ParameterType.TOGGLED)}}
    result = BlendStop.adjust_binary_params(diff_map)
    val_a, val_b, _ = result["/Fx"]["Switch"]
    assert val_a == pytest.approx(1.0)
    assert val_b == pytest.approx(1.0)


def test_adjust_binary_params_bypass_symbol_on_wins_regardless_of_type():
    diff_map = {"/Fx": {":bypass": (1.0, 0.0, ParameterType.DEFAULT)}}
    result = BlendStop.adjust_binary_params(diff_map)
    val_a, val_b, _ = result["/Fx"][":bypass"]
    assert val_a == pytest.approx(1.0)
    assert val_b == pytest.approx(1.0)


def test_adjust_binary_params_default_type_unchanged():
    diff_map = {"/Fx": {"Vol": (0.2, 0.8, ParameterType.DEFAULT)}}
    result = BlendStop.adjust_binary_params(diff_map)
    val_a, val_b, _ = result["/Fx"]["Vol"]
    assert val_a == pytest.approx(0.2)
    assert val_b == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# build_enriched_diff_map — MIDI-bound exclusion
# ---------------------------------------------------------------------------


def test_build_enriched_diff_map_excludes_midi_bound_param():
    lower = BlendStop(0.0, 0, {"/Fx": {"Vol": 0.0, "Bound": 0.0}})
    upper = BlendStop(1.0, 1, {"/Fx": {"Vol": 1.0, "Bound": 1.0}})
    midi_bound = {("/Fx", "Bound")}

    result = BlendStop.build_enriched_diff_map(
        lower, upper, lambda i, s: ParameterType.DEFAULT, midi_bound
    )

    assert "Vol" in result.get("/Fx", {})
    assert "Bound" not in result.get("/Fx", {})


def test_build_enriched_diff_map_removes_instance_when_all_params_excluded():
    lower = BlendStop(0.0, 0, {"/Fx": {"Bound": 0.0}})
    upper = BlendStop(1.0, 1, {"/Fx": {"Bound": 1.0}})
    midi_bound = {("/Fx", "Bound")}

    result = BlendStop.build_enriched_diff_map(
        lower, upper, lambda i, s: ParameterType.DEFAULT, midi_bound
    )

    assert "/Fx" not in result
