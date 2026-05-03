"""Unit tests for blend/easing.py — easing functions."""

import math

import pytest

from blend.easing import (
    ease_in_cubic,
    ease_in_out_cubic,
    ease_in_out_quad,
    ease_in_quad,
    ease_out_cubic,
    ease_out_quad,
    exponential_easing,
    sine_easing,
)


# ---------------------------------------------------------------------------
# Midpoint bias — ease_in variants are slower at the start (f(0.5) < 0.5)
# ---------------------------------------------------------------------------


def test_ease_in_quad_midpoint_below_half():
    assert ease_in_quad(0.5) < 0.5


def test_ease_in_cubic_midpoint_below_half():
    assert ease_in_cubic(0.5) < 0.5


def test_exponential_midpoint_well_below_half():
    # 2^(10*(0.5-1)) = 2^(-5) ≈ 0.031
    assert exponential_easing(0.5) == pytest.approx(2 ** -5, rel=1e-6)
    assert exponential_easing(0.5) < 0.1


# ---------------------------------------------------------------------------
# Midpoint bias — ease_out variants are faster at the start (f(0.5) > 0.5)
# ---------------------------------------------------------------------------


def test_ease_out_quad_midpoint_above_half():
    assert ease_out_quad(0.5) > 0.5


def test_ease_out_cubic_midpoint_above_half():
    assert ease_out_cubic(0.5) > 0.5


def test_sine_easing_midpoint_above_half():
    # sin(π*0.5/2) = sin(π/4) ≈ 0.707
    assert sine_easing(0.5) == pytest.approx(math.sin(math.pi / 4), rel=1e-9)
    assert sine_easing(0.5) > 0.5


def test_ease_in_out_quad_midpoint_at_half():
    assert ease_in_out_quad(0.5) == pytest.approx(0.5)


def test_ease_in_out_cubic_midpoint_at_half():
    assert ease_in_out_cubic(0.5) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# exponential_easing boundary clamps (special-cased in code)
# ---------------------------------------------------------------------------


def test_exponential_easing_exactly_zero_at_zero():
    assert exponential_easing(0.0) == 0.0


def test_exponential_easing_exactly_one_at_one():
    assert exponential_easing(1.0) == 1.0
