"""Unit tests for StrobeWidget._flush_spans — the per-tick refresh coalescer.

_flush_spans takes a list of (x, width) column spans (which may wrap past _W),
splits wraps, sorts, merges spans within _MERGE_GAP of each other, and emits one
self.refresh(Box) per merged run — each box spanning the widget's full height.
These tests exercise that logic in isolation (no LCD / panel stack) by capturing
the refresh calls.
"""

import pytest

from uilib.box import Box
from pistomp.tuner.panel import StrobeWidget, _W

STROBE_BOX = Box.xywh(0, 81, 320, 127)  # mirrors TunerPanel's strobe geometry
GAP = StrobeWidget._MERGE_GAP           # == STRIPE_W (4)


def make_widget():
    """A bare StrobeWidget whose refresh() records the boxes it's handed."""
    w = StrobeWidget(box=STROBE_BOX.copy())
    calls: list[Box] = []
    w.refresh = lambda b=None: calls.append(b)  # type: ignore[assignment]
    return w, calls


def runs(calls):
    """Emitted boxes as (x0, x1); assert each spans the full widget height."""
    out = []
    for b in calls:
        assert b.y0 == STROBE_BOX.y0
        assert b.y1 == STROBE_BOX.y1
        out.append((b.x0, b.x1))
    return out


# ── degenerate inputs ──────────────────────────────────────────────────────────

def test_empty_spans_emit_nothing():
    w, calls = make_widget()
    w._flush_spans([])
    assert calls == []


def test_zero_and_negative_width_skipped():
    w, calls = make_widget()
    w._flush_spans([(10, 0), (20, -5)])
    assert calls == []


def test_box_none_emits_nothing():
    w, calls = make_widget()
    w.box = None
    w._flush_spans([(10, 4)])
    assert calls == []


# ── single span ────────────────────────────────────────────────────────────────

def test_single_span_one_full_height_box():
    w, calls = make_widget()
    w._flush_spans([(40, 6)])
    assert runs(calls) == [(40, 46)]


# ── coalescing ─────────────────────────────────────────────────────────────────

def test_overlapping_spans_coalesce():
    w, calls = make_widget()
    w._flush_spans([(10, 8), (14, 8)])  # [10,18) and [14,22) overlap
    assert runs(calls) == [(10, 22)]


def test_contained_span_absorbed():
    w, calls = make_widget()
    w._flush_spans([(10, 20), (14, 2)])  # [14,16) inside [10,30)
    assert runs(calls) == [(10, 30)]


def test_adjacent_within_gap_coalesce():
    # gap exactly == _MERGE_GAP must merge: next.start <= cur.end + GAP
    w, calls = make_widget()
    w._flush_spans([(10, 2), (12 + GAP, 2)])  # [10,12) and [12+GAP, ...)
    assert runs(calls) == [(10, 14 + GAP)]


def test_separated_beyond_gap_stay_split():
    # one past the gap must NOT merge
    w, calls = make_widget()
    w._flush_spans([(10, 2), (13 + GAP, 2)])  # gap == GAP+1
    assert runs(calls) == [(10, 12), (13 + GAP, 15 + GAP)]


def test_unsorted_input_is_sorted_then_merged():
    w, calls = make_widget()
    w._flush_spans([(200, 4), (10, 2), (12, 2)])
    assert runs(calls) == [(10, 14), (200, 204)]


def test_emitted_runs_are_ascending():
    w, calls = make_widget()
    w._flush_spans([(300, 4), (100, 4), (50, 4)])
    xs = [x0 for x0, _ in runs(calls)]
    assert xs == sorted(xs)


# ── wrap handling ──────────────────────────────────────────────────────────────

def test_wrap_splits_into_two_runs():
    w, calls = make_widget()
    w._flush_spans([(_W - 2, 5)])  # [318,323) -> [318,320) + [0,3)
    assert runs(calls) == [(0, 3), (_W - 2, _W)]


def test_wrap_remainder_coalesces_with_low_span():
    w, calls = make_widget()
    # wrap tail lands at [0,2); a nearby low span [1,3) should merge with it,
    # while the right-edge piece [318,320) stays its own transaction.
    w._flush_spans([(_W - 2, 4), (1, 2)])
    assert runs(calls) == [(0, 3), (_W - 2, _W)]


def test_wrap_tail_and_right_edge_never_merge_across_seam():
    w, calls = make_widget()
    # the two halves of a single wrapped span are far apart in x-space, so they
    # must remain two boxes (no SPI window can straddle the seam).
    w._flush_spans([(_W - 1, 2)])  # [319,321) -> [319,320) + [0,1)
    assert runs(calls) == [(0, 1), (_W - 1, _W)]


# ── realistic strobe patterns ──────────────────────────────────────────────────

def test_stripe_tail_and_lead_coalesce_to_one_box():
    # slow-path emission for a single stripe: tail at x and lead at x+STRIPE_W,
    # each `ak` wide with ak < STRIPE_W, must collapse to one span of width
    # STRIPE_W + ak.
    w, calls = make_widget()
    ak = 2
    x = 50
    w._flush_spans([(x, ak), (x + StrobeWidget.STRIPE_W, ak)])
    assert runs(calls) == [(x, x + StrobeWidget.STRIPE_W + ak)]


def test_six_spaced_stripes_stay_separate():
    # 6 stripes one STRIPE_P apart are far beyond the merge gap -> 6 boxes.
    w, calls = make_widget()
    spans = w._stripe_spans_at(0)
    w._flush_spans(spans)
    sw = StrobeWidget.STRIPE_W
    expected = [
        (i * StrobeWidget.STRIPE_P, i * StrobeWidget.STRIPE_P + sw)
        for i in range(StrobeWidget.N_STRIPES)
    ]
    assert runs(calls) == expected
