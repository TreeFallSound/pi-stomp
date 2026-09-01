"""
ScrollingText selection gating.

Every scroll step is a repaint, repaints are SPI traffic, and SPI traffic is
audible on the DAC at high gain. So a long title must not animate by default:
ping-pong auto-scroll runs only while the widget is the one NAV selected, and
an unselected widget sits snapped at the text's start. Exactly 0 or 1
ScrollingTexts animate at any moment, with no extra state — the widget's own
`selected` flag (maintained by the panel's nav machinery) is the whole gate.

Contracts verified here:
  - unselected widgets never advance the scroll offset, at any clock time
  - a selected widget ping-pongs 0 -> max -> 0 and parks at each end
  - deselection snaps back to the leftmost position immediately
  - text that fits never scrolls
  - a real Panel with two overflow titles has at most one scroller moving
"""

import pytest

from common.fonts import font_path
from tests.conftest import FakeClock
from uilib.box import Box
from uilib.panel import Panel
from uilib.pygame_init import font as make_font
from uilib.text import ScrollingText


LONG = "The Extremely Long Pedalboard Name That Will Not Fit"
SHORT = "Rig"

# A tick cadence well under the 0.25s re-anchor gap so ticks look continuous
# to the widget, letting the test sweep a whole cycle in coarse steps.
DT = 0.1


@pytest.fixture
def font():
    """A fresh font per test: emulator suites quit pygame mid-session, which
    invalidates any font created earlier (including at import time)."""
    return make_font(font_path("DejaVuSans.ttf"), 26)


def make_text(font, text=LONG, width=60, parent=None):
    w = ScrollingText(
        box=Box.xywh(0, 0, width, 36),
        text=text,
        font=font,
        parent=parent,
    )
    assert w.box is not None
    return w


def make_panel():
    p = Panel(box=Box.xywh(0, 0, 320, 240))
    p.visible = True
    return p


def max_offset_of(w):
    h_margin, _ = w._get_margins()
    return w.cached_text_width - (w.box.width - h_margin - w.outline)


@pytest.fixture
def clock(monkeypatch):
    return FakeClock(monkeypatch)


# ---------------------------------------------------------------------------
# The gate: unselected widgets never move
# ---------------------------------------------------------------------------


def test_unselected_never_scrolls(clock, font):
    w = make_text(font)
    w._render_text_to_cache()
    assert w._should_scroll(), "fixture must overflow"

    # A full cycle plus change, ticked as if the mainloop were running.
    end = w.pause_start_sec + (max_offset_of(w) / w.pixels_per_second) * 2 + w.pause_end_sec + 5.0
    t = 0.0
    while t < end:
        t += DT
        clock.now = t
        w.tick()
        assert w.scroll_offset == 0, f"unselected widget scrolled to {w.scroll_offset} at t={t}"


def test_hidden_never_scrolls(clock, font):
    w = make_text(font)
    w.selected = True
    w.visible = False
    clock.drive(w, DT, n=60)
    assert w.scroll_offset == 0


# ---------------------------------------------------------------------------
# Selected widgets ping-pong
# ---------------------------------------------------------------------------


def test_selected_scrolls_and_pingpongs(clock, font):
    w = make_text(font)
    w._render_text_to_cache()
    w.selected = True

    max_off = max_offset_of(w)
    scroll_dur = max_off / w.pixels_per_second

    # First tick anchors the cycle; every phase boundary below is relative
    # to that anchor, not to zero.
    clock.drive(w, DT)
    t0 = clock.now

    # Through the start pause: parked at 0.
    while clock.now < t0 + w.pause_start_sec:
        clock.drive(w, DT)
    assert w.scroll_offset == 0

    # Down the text: rising monotonically to max.
    last = 0
    t_end = t0 + w.pause_start_sec + scroll_dur
    while clock.now < t_end:
        clock.drive(w, DT)
        assert w.scroll_offset >= last
        last = w.scroll_offset
    clock.now = t_end
    w.tick()
    assert w.scroll_offset == max_off

    # The end pause: parked at max.
    while clock.now < t_end + w.pause_end_sec:
        clock.drive(w, DT)
    assert w.scroll_offset == max_off

    # And back home to exactly 0 by the end of the return phase.
    t_home = t_end + w.pause_end_sec + scroll_dur
    while clock.now < t_home:
        clock.drive(w, DT)
    clock.now = t_home
    w.tick()
    assert w.scroll_offset == 0


def test_text_that_fits_never_scrolls(clock, font):
    w = make_text(font, text=SHORT, width=200)
    w.selected = True
    clock.drive(w, DT, n=100)
    assert w.scroll_offset == 0


# ---------------------------------------------------------------------------
# Snap home on deselect
# ---------------------------------------------------------------------------


def test_deselect_snaps_home_and_stays(clock, font):
    w = make_text(font)
    w._render_text_to_cache()
    w.selected = True

    # Scroll to the far end of the text.
    max_off = max_offset_of(w)
    clock.drive(w, DT)
    t0 = clock.now
    while clock.now < t0 + w.pause_start_sec + max_off / w.pixels_per_second:
        clock.drive(w, DT)
    assert w.scroll_offset == max_off

    # Deselect: parked at the leftmost position immediately, in the same
    # repaint that drops the selection reticule.
    w.set_selected(False)
    assert w.scroll_offset == 0

    # And it stays there, forever, for free.
    clock.drive(w, DT, n=200)
    assert w.scroll_offset == 0
    assert w._anchor_time is None


# ---------------------------------------------------------------------------
# The invariant, against the real panel selection machinery
# ---------------------------------------------------------------------------


def test_panel_selection_moves_the_single_scroller(clock, font):
    panel = make_panel()
    a = make_text(font, parent=panel, width=60)
    b = make_text(font, parent=panel, width=60)
    panel.add_sel_widget(a)
    panel.add_sel_widget(b)
    panel.sel_ref = a
    a.selected = True
    a._render_text_to_cache()
    b._render_text_to_cache()

    def offsets():
        return (a.scroll_offset, b.scroll_offset)

    # First selection: exactly one widget may animate.
    clock.drive(a, DT, n=int((a.pause_start_sec + max_offset_of(a) / a.pixels_per_second * 0.5) / DT))
    oa, ob = offsets()
    assert oa > 0
    assert ob == 0

    # NAV to the second: the first snapped home, the second took over.
    panel.sel_widget(b)
    clock.drive(b, DT, n=int((b.pause_start_sec + max_offset_of(b) / b.pixels_per_second * 0.5) / DT))
    assert a.scroll_offset == 0
    assert b.scroll_offset > 0

    # NAV off both (a menu is open; the title widgets lose selection):
    # nothing animates at all.
    panel.sel_widget(_plain_widget(panel, font))
    clock.drive(a, DT, n=50)
    clock.drive(b, DT, n=50)
    assert offsets() == (0, 0)


def _plain_widget(panel, font):
    from uilib.text import TextWidget

    w = TextWidget(box=Box.xywh(0, 100, 60, 36), text="plain", font=font, parent=panel)
    panel.add_sel_widget(w)
    return w