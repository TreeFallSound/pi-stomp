"""Unit tests for blend/easing.py — easing functions."""

import math

import pytest

from blend.easing import (
    EASING_FUNCTIONS,
    bloom,
    build,
    drop,
    linear,
    smooth,
    snap,
)


# ---------------------------------------------------------------------------
# Boundary conditions — all functions must map 0→0 and 1→1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("func", EASING_FUNCTIONS.values())
def test_easing_zero_at_zero(func):
    assert func(0.0) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("func", EASING_FUNCTIONS.values())
def test_easing_one_at_one(func):
    assert func(1.0) == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# linear — identity
# ---------------------------------------------------------------------------


def test_linear_midpoint():
    assert linear(0.5) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# smooth — symmetric ease-in-out, midpoint at 0.5
# ---------------------------------------------------------------------------


def test_smooth_midpoint_at_half():
    assert smooth(0.5) == pytest.approx(0.5)


def test_smooth_slow_at_start():
    # ease-in-out: should be below linear near the start
    assert smooth(0.25) < 0.25


def test_smooth_fast_in_middle():
    # ease-in-out: should be above linear just before midpoint
    assert smooth(0.4) < 0.5


# ---------------------------------------------------------------------------
# build — ease-in cubic, slow start
# ---------------------------------------------------------------------------


def test_build_midpoint_below_half():
    assert build(0.5) < 0.5


def test_build_more_extreme_than_smooth_at_quarter():
    assert build(0.25) < smooth(0.25)


# ---------------------------------------------------------------------------
# drop — ease-out cubic, fast start
# ---------------------------------------------------------------------------


def test_drop_midpoint_above_half():
    assert drop(0.5) > 0.5


def test_drop_more_extreme_than_smooth_at_quarter():
    assert drop(0.25) > smooth(0.25)


# ---------------------------------------------------------------------------
# snap — exponential, stays near zero then jumps
# ---------------------------------------------------------------------------


def test_snap_midpoint_well_below_half():
    assert snap(0.5) < 0.1


def test_snap_zero_at_zero():
    assert snap(0.0) == 0.0


def test_snap_one_at_one():
    assert snap(1.0) == 1.0


# ---------------------------------------------------------------------------
# bloom — sqrt, immediate big shift then plateaus
# ---------------------------------------------------------------------------


def test_bloom_midpoint_above_half():
    assert bloom(0.5) == pytest.approx(math.sqrt(0.5))
    assert bloom(0.5) > 0.5


def test_bloom_faster_than_drop_near_start():
    # sqrt gains value faster than ease-out cubic at very small t
    assert bloom(0.1) > drop(0.1)


# ---------------------------------------------------------------------------
# EASING_FUNCTIONS dict contains all named functions
# ---------------------------------------------------------------------------


def test_easing_functions_keys():
    assert set(EASING_FUNCTIONS.keys()) == {"linear", "smooth", "build", "drop", "snap", "bloom"}
