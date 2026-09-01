
import pytest

from common.fonts import font_path
from tests.conftest import FakeClock
from uilib.box import Box
from uilib.panel import Panel
from uilib.pygame_init import font as make_font
from uilib.text import ScrollingText


LONG = "The Extremely Long Pedalboard Name That Will Not Fit"
SHORT = "Rig"

DT = 0.1


@pytest.fixture
def font():
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




def test_unselected_never_scrolls(clock, font):
    w = make_text(font)
    w._render_text_to_cache()
    assert w._should_scroll(), "fixture must overflow"

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




def test_selected_scrolls_and_pingpongs(clock, font):
    w = make_text(font)
    w._render_text_to_cache()
    w.selected = True

    max_off = max_offset_of(w)
    scroll_dur = max_off / w.pixels_per_second

    clock.drive(w, DT)
    t0 = clock.now

    while clock.now < t0 + w.pause_start_sec:
        clock.drive(w, DT)
    assert w.scroll_offset == 0

    last = 0
    t_end = t0 + w.pause_start_sec + scroll_dur
    while clock.now < t_end:
        clock.drive(w, DT)
        assert w.scroll_offset >= last
        last = w.scroll_offset
    clock.now = t_end
    w.tick()
    assert w.scroll_offset == max_off

    while clock.now < t_end + w.pause_end_sec:
        clock.drive(w, DT)
    assert w.scroll_offset == max_off

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




def test_deselect_snaps_home_and_stays(clock, font):
    w = make_text(font)
    w._render_text_to_cache()
    w.selected = True

    max_off = max_offset_of(w)
    clock.drive(w, DT)
    t0 = clock.now
    while clock.now < t0 + w.pause_start_sec + max_off / w.pixels_per_second:
        clock.drive(w, DT)
    assert w.scroll_offset == max_off

    w.set_selected(False)
    assert w.scroll_offset == 0

    clock.drive(w, DT, n=200)
    assert w.scroll_offset == 0
    assert w._anchor_time is None




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

    clock.drive(a, DT, n=int((a.pause_start_sec + max_offset_of(a) / a.pixels_per_second * 0.5) / DT))
    oa, ob = offsets()
    assert oa > 0
    assert ob == 0

    panel.sel_widget(b)
    clock.drive(b, DT, n=int((b.pause_start_sec + max_offset_of(b) / b.pixels_per_second * 0.5) / DT))
    assert a.scroll_offset == 0
    assert b.scroll_offset > 0

    panel.sel_widget(_plain_widget(panel, font))
    clock.drive(a, DT, n=50)
    clock.drive(b, DT, n=50)
    assert offsets() == (0, 0)


def _plain_widget(panel, font):
    from uilib.text import TextWidget

    w = TextWidget(box=Box.xywh(0, 100, 60, 36), text="plain", font=font, parent=panel)
    panel.add_sel_widget(w)
    return w