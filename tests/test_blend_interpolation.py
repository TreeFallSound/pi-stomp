"""Unit tests for blend/interpolation.py — spline and easing-based interpolation."""

import pytest

from blend.interpolation import (
    catmull_rom_interpolation,
    ease_in_cubic_interpolation,
    ease_in_out_cubic_interpolation,
    ease_in_out_quad_interpolation,
    ease_in_quad_interpolation,
    ease_out_cubic_interpolation,
    ease_out_quad_interpolation,
    exponential_easing_interpolation,
    hermite_interpolation,
    linear_interpolation,
    sine_easing_interpolation,
)
from blend.types import ParamData
from modalapi.parameter import Type as ParameterType


def _pd(val_a: float, val_b: float, prev_val=None, next_val=None, segment_range: float = 1.0) -> ParamData:
    return ParamData(
        val_a=val_a,
        val_b=val_b,
        prev_val=prev_val,
        next_val=next_val,
        segment_range=segment_range,
        param_type=ParameterType.DEFAULT,
    )


# ---------------------------------------------------------------------------
# hermite_interpolation
# ---------------------------------------------------------------------------


def test_hermite_passes_through_endpoints():
    pd = _pd(0.3, 0.9)
    assert hermite_interpolation(0.0, pd) == pytest.approx(0.3, rel=1e-6)
    assert hermite_interpolation(1.0, pd) == pytest.approx(0.9, rel=1e-6)


def test_hermite_with_prev_neighbor_stays_monotone():
    pd = _pd(0.5, 1.0, prev_val=0.0, segment_range=0.5)
    midpoint = hermite_interpolation(0.5, pd)
    assert 0.5 < midpoint < 1.0


def test_hermite_with_next_neighbor_passes_through_endpoints():
    pd = _pd(0.0, 0.5, next_val=1.0, segment_range=0.5)
    assert hermite_interpolation(0.0, pd) == pytest.approx(0.0, rel=1e-6)
    assert hermite_interpolation(1.0, pd) == pytest.approx(0.5, rel=1e-6)


# ---------------------------------------------------------------------------
# catmull_rom_interpolation
# ---------------------------------------------------------------------------


def test_catmull_rom_passes_through_endpoints_without_neighbors():
    pd = _pd(0.0, 1.0)
    assert catmull_rom_interpolation(0.0, pd) == pytest.approx(0.0, rel=1e-6)
    assert catmull_rom_interpolation(1.0, pd) == pytest.approx(1.0, rel=1e-6)


def test_catmull_rom_passes_through_endpoints_with_neighbors():
    pd = _pd(0.3, 0.7, prev_val=0.0, next_val=1.0)
    assert catmull_rom_interpolation(0.0, pd) == pytest.approx(0.3, rel=1e-6)
    assert catmull_rom_interpolation(1.0, pd) == pytest.approx(0.7, rel=1e-6)


# ---------------------------------------------------------------------------
# Easing interpolations — midpoint bias and endpoint correctness
# ---------------------------------------------------------------------------


def test_ease_in_quad_interpolation_midpoint_below_linear():
    pd = _pd(0.0, 1.0)
    assert ease_in_quad_interpolation(0.5, pd) < linear_interpolation(0.5, pd)


def test_ease_out_quad_interpolation_midpoint_above_linear():
    pd = _pd(0.0, 1.0)
    assert ease_out_quad_interpolation(0.5, pd) > linear_interpolation(0.5, pd)


def test_ease_in_out_quad_interpolation_midpoint_equals_linear():
    pd = _pd(0.0, 1.0)
    assert ease_in_out_quad_interpolation(0.5, pd) == pytest.approx(linear_interpolation(0.5, pd), rel=1e-9)


def test_ease_in_cubic_interpolation_more_extreme_than_quad():
    pd = _pd(0.0, 1.0)
    assert ease_in_cubic_interpolation(0.5, pd) < ease_in_quad_interpolation(0.5, pd)


def test_ease_out_cubic_interpolation_more_extreme_than_quad():
    pd = _pd(0.0, 1.0)
    assert ease_out_cubic_interpolation(0.5, pd) > ease_out_quad_interpolation(0.5, pd)


def test_ease_in_out_cubic_interpolation_midpoint_equals_linear():
    pd = _pd(0.0, 1.0)
    assert ease_in_out_cubic_interpolation(0.5, pd) == pytest.approx(0.5, rel=1e-9)


def test_exponential_easing_interpolation_midpoint_well_below_linear():
    pd = _pd(0.0, 1.0)
    assert exponential_easing_interpolation(0.5, pd) < 0.1


def test_sine_easing_interpolation_midpoint_above_linear():
    pd = _pd(0.0, 1.0)
    assert sine_easing_interpolation(0.5, pd) > linear_interpolation(0.5, pd)


def test_easing_interpolation_respects_val_a_val_b_range():
    # At endpoints the value must equal val_a and val_b regardless of range
    pd = _pd(0.2, 0.8)
    assert ease_in_quad_interpolation(0.0, pd) == pytest.approx(0.2, rel=1e-9)
    assert ease_in_quad_interpolation(1.0, pd) == pytest.approx(0.8, rel=1e-9)
