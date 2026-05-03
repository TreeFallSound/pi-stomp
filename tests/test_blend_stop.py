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
    stops = [lower, upper]
    midi_bound = {("/Fx", "Bound")}

    result = BlendStop.build_enriched_diff_map(
        lower, upper, stops, 0, lambda i, s: ParameterType.DEFAULT, midi_bound
    )

    assert "Vol" in result.get("/Fx", {})
    assert "Bound" not in result.get("/Fx", {})


def test_build_enriched_diff_map_removes_instance_when_all_params_excluded():
    lower = BlendStop(0.0, 0, {"/Fx": {"Bound": 0.0}})
    upper = BlendStop(1.0, 1, {"/Fx": {"Bound": 1.0}})
    stops = [lower, upper]
    midi_bound = {("/Fx", "Bound")}

    result = BlendStop.build_enriched_diff_map(
        lower, upper, stops, 0, lambda i, s: ParameterType.DEFAULT, midi_bound
    )

    assert "/Fx" not in result


# ---------------------------------------------------------------------------
# build_enriched_diff_map — neighbor value lookup
# ---------------------------------------------------------------------------


def test_build_enriched_diff_map_includes_prev_val_for_interior_segment():
    stop0 = BlendStop(0.0, 0, {"/Fx": {"Vol": 0.1}})
    stop1 = BlendStop(0.5, 1, {"/Fx": {"Vol": 0.5}})
    stop2 = BlendStop(1.0, 2, {"/Fx": {"Vol": 0.9}})
    stops = [stop0, stop1, stop2]

    result = BlendStop.build_enriched_diff_map(
        stop1, stop2, stops, 1, lambda i, s: ParameterType.DEFAULT, None
    )

    param = result["/Fx"]["Vol"]
    assert param.prev_val == pytest.approx(0.1)  # stops[0]
    assert param.next_val is None  # segment_idx=1, len(stops)-2=1 → not <


def test_build_enriched_diff_map_includes_next_val_for_first_segment():
    stop0 = BlendStop(0.0, 0, {"/Fx": {"Vol": 0.1}})
    stop1 = BlendStop(0.5, 1, {"/Fx": {"Vol": 0.5}})
    stop2 = BlendStop(1.0, 2, {"/Fx": {"Vol": 0.9}})
    stops = [stop0, stop1, stop2]

    result = BlendStop.build_enriched_diff_map(
        stop0, stop1, stops, 0, lambda i, s: ParameterType.DEFAULT, None
    )

    param = result["/Fx"]["Vol"]
    assert param.prev_val is None  # segment_idx=0, no previous
    assert param.next_val == pytest.approx(0.9)  # stops[0+2] = stops[2]


def test_build_enriched_diff_map_no_neighbors_for_two_stop_segment():
    lower = BlendStop(0.0, 0, {"/Fx": {"Vol": 0.0}})
    upper = BlendStop(1.0, 1, {"/Fx": {"Vol": 1.0}})
    stops = [lower, upper]

    result = BlendStop.build_enriched_diff_map(
        lower, upper, stops, 0, lambda i, s: ParameterType.DEFAULT, None
    )

    param = result["/Fx"]["Vol"]
    assert param.prev_val is None
    assert param.next_val is None
