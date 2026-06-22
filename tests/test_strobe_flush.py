"""Unit tests for StrobeWidget._flush_spans — the per-tick refresh coalescer.

_flush_spans takes a list of (x, width) column spans (which may wrap past _W),
splits wraps, sorts, merges spans within _MERGE_GAP of each other, and accumulates
the result into self._pending via Box.union(). tick() then issues a single
self.refresh(_pending). These tests exercise _flush_spans in isolation by inspecting
_pending after each call.
"""

from uilib.box import Box
from pistomp.tuner.panel import StrobeWidget, _W

STROBE_BOX = Box.xywh(0, 81, 320, 127)  # mirrors TunerPanel's strobe geometry


def make_widget():
    w = StrobeWidget(box=STROBE_BOX.copy())
    return w


def pending_x(w):
    """Return _pending as (x0, x1) verifying full height, or None."""
    if w._pending is None:
        return None
    b = w._pending
    assert b.y0 == STROBE_BOX.y0
    assert b.y1 == STROBE_BOX.y1
    return (b.x0, b.x1)


# ── degenerate inputs ──────────────────────────────────────────────────────────


def test_empty_spans_emit_nothing():
    w = make_widget()
    w._flush_spans([])
    assert w._pending is None


def test_zero_and_negative_width_skipped():
    w = make_widget()
    w._flush_spans([(10, 0), (20, -5)])
    assert w._pending is None


def test_box_none_emits_nothing():
    w = make_widget()
    w.box = None
    w._flush_spans([(10, 4)])
    assert w._pending is None


# ── single span ────────────────────────────────────────────────────────────────


def test_single_span_one_full_height_box():
    w = make_widget()
    w._flush_spans([(40, 6)])
    assert pending_x(w) == (40, 46)


# ── coalescing ─────────────────────────────────────────────────────────────────


def test_overlapping_spans_coalesce():
    w = make_widget()
    w._flush_spans([(10, 8), (14, 8)])  # [10,18) and [14,22) overlap
    assert pending_x(w) == (10, 22)


def test_contained_span_absorbed():
    w = make_widget()
    w._flush_spans([(10, 20), (14, 2)])  # [14,16) inside [10,30)
    assert pending_x(w) == (10, 30)


def test_adjacent_spans_union():
    w = make_widget()
    w._flush_spans([(10, 2), (16, 2)])  # [10,12) and [16,18)
    assert pending_x(w) == (10, 18)


def test_separated_spans_union_into_one_pending():
    w = make_widget()
    w._flush_spans([(10, 2), (100, 2)])  # far apart
    assert pending_x(w) == (10, 102)


def test_unsorted_input_covered_by_pending():
    w = make_widget()
    w._flush_spans([(200, 4), (10, 2), (12, 2)])
    x0, x1 = pending_x(w)
    assert x0 <= 10 and x1 >= 204


# ── wrap handling ──────────────────────────────────────────────────────────────


def test_wrap_splits_into_two_runs():
    # [318,323) -> [318,320) + [0,3); pending is their union (full width)
    w = make_widget()
    w._flush_spans([(_W - 2, 5)])
    assert pending_x(w) == (0, _W)


def test_wrap_remainder_coalesces_with_low_span():
    w = make_widget()
    w._flush_spans([(_W - 2, 4), (1, 2)])
    assert pending_x(w) == (0, _W)


def test_wrap_tail_and_right_edge_in_pending():
    w = make_widget()
    w._flush_spans([(_W - 1, 2)])  # [319,321) -> [319,320) + [0,1)
    assert pending_x(w) == (0, _W)


# ── realistic strobe patterns ──────────────────────────────────────────────────


def test_stripe_tail_and_lead_in_pending():
    w = make_widget()
    ak = 2
    x = 50
    w._flush_spans([(x, ak), (x + StrobeWidget.STRIPE_W, ak)])
    x0, x1 = pending_x(w)
    assert x0 <= x and x1 >= x + StrobeWidget.STRIPE_W + ak


def test_six_spaced_stripes_union_into_one_pending():
    # 6 stripes all end up in one _pending box covering all of them
    w = make_widget()
    spans = w._stripe_spans_at(0)
    w._flush_spans(spans)
    x0, x1 = pending_x(w)
    sw = StrobeWidget.STRIPE_W
    assert x0 == 0
    assert x1 == (StrobeWidget.N_STRIPES - 1) * StrobeWidget.STRIPE_P + sw


def test_flush_spans_does_not_call_refresh_directly():
    # refresh is called once by tick(), never by _flush_spans
    w = make_widget()
    calls = []
    w.refresh = lambda b=None: calls.append(b)
    w._flush_spans([(40, 6)])
    assert calls == []
    assert w._pending is not None
