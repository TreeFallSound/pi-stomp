"""
Unit tests for ContainerWidget scroll-into-view logic, including the
policy hook (_scroll_delta) used by Menu to scroll pixel-precise vertically
instead of page-snapping in both axes.
"""

from uilib.box import Box
from uilib.container import ContainerWidget


def make_container(w=240, h=200, content_height=None):
    kwargs = {}
    if content_height is not None:
        kwargs['virtual'] = True
        kwargs['content_height'] = content_height
    return ContainerWidget(box=Box.xywh(0, 0, w, h), **kwargs)


class PixelVerticalContainer(ContainerWidget):
    """Stand-in for Menu's scroll policy: vertical-only, pixel-precise."""

    def _scroll_delta(self, box, movex, movey, orig_box):
        return 0, movey


def make_pixel_container(w=240, h=200, content_height=None):
    kwargs = {}
    if content_height is not None:
        kwargs['virtual'] = True
        kwargs['content_height'] = content_height
    return PixelVerticalContainer(box=Box.xywh(0, 0, w, h), **kwargs)


# ---------------------------------------------------------------------------
# Default policy: ContainerWidget._scroll_delta (page-snap + y0==0 reset)
# ---------------------------------------------------------------------------


def test_no_overflow_returns_false_and_leaves_offset():
    c = make_container(content_height=400)
    visible_child = Box.xywh(0, 50, 240, 40)
    assert c._scroll_into_view(visible_child) is False
    assert c.offset == (0, 0)


def test_overflow_below_page_snaps_by_box_height():
    # Child at y=240..280 in a 200-tall viewport overflows by 80.
    # Page-snap rounds 80 up to a multiple of child height (40) -> 80.
    c = make_container(content_height=400)
    c._scroll_into_view(Box.xywh(0, 240, 240, 40))
    assert c.offset == (0, 80)


def test_overflow_above_page_snaps_negative():
    c = make_container(content_height=400)
    c.scroll((0, 120))
    # A child at layout y=40..80 is at screen y=-80..-40 (above viewport).
    # movey = -80; page-snap by child height (40) -> -80.
    c._scroll_into_view(Box.xywh(0, 40, 240, 40))
    assert c.offset == (0, 40)


def test_y0_zero_resets_y_to_zero():
    # Default policy snaps oy back to 0 when orig box.y0 == 0,
    # regardless of computed page-snap delta. Preserves legacy
    # behavior of commit e9529ac.
    c = make_container(content_height=400)
    c.scroll((0, 160))
    c._scroll_into_view(Box.xywh(0, 0, 240, 40))
    assert c.offset == (0, 0)


# ---------------------------------------------------------------------------
# Menu policy (vertical, pixel-precise, no y0==0 reset)
# ---------------------------------------------------------------------------


def test_pixel_policy_scrolls_exactly_overflow_amount():
    # Item at y=240..280 overflows 200-tall viewport by 80.
    # Pixel policy uses movey directly, no rounding.
    c = make_pixel_container(content_height=400)
    c._scroll_into_view(Box.xywh(0, 240, 240, 35))  # y1=275, overflow=75
    assert c.offset == (0, 75)


def test_pixel_policy_locks_x_axis():
    # Even if horizontal overflow exists, vertical policy returns dx=0.
    c = make_pixel_container(content_height=400)
    c._scroll_into_view(Box.xywh(300, 50, 60, 30))
    assert c.offset == (0, 0)


def test_pixel_policy_does_not_apply_y0_zero_reset():
    # Menu items at y=0 should NOT trigger the legacy reset hack.
    # If the topmost item is already visible (no overflow), no scroll occurs.
    c = make_pixel_container(content_height=400)
    c.scroll((0, 120))
    # Item at layout y=0..40; with offset 120 it's at screen y=-120..-80
    # → movey=-120 → policy returns (0, -120) → offset becomes (0, 0).
    c._scroll_into_view(Box.xywh(0, 0, 240, 40))
    assert c.offset == (0, 0)


def test_pixel_policy_partial_overflow_bottom():
    # Item only partially below viewport bottom: scroll by the exact
    # number of pixels needed to bring its y1 to the viewport edge.
    c = make_pixel_container(content_height=400)
    c._scroll_into_view(Box.xywh(0, 180, 240, 50))  # y1=230, overflow=30
    assert c.offset == (0, 30)


# ---------------------------------------------------------------------------
# Non-virtual container: scroll delegates to parent
# ---------------------------------------------------------------------------


def test_non_virtual_container_delegates_scroll_to_parent():
    # A non-virtual container should not scroll itself; it should pass
    # the request up to a virtual ancestor.
    parent = make_container(content_height=400)
    child = ContainerWidget(box=Box.xywh(0, 0, 240, 200))
    child.attach(parent)
    # Child box overflowing in parent's content coords
    child._scroll_into_view(Box.xywh(0, 240, 240, 40))
    assert child.offset == (0, 0)
    assert parent.offset == (0, 80)


# ---------------------------------------------------------------------------
# Render coordinate trace: verifies the offset convention
# ---------------------------------------------------------------------------


def test_offset_convention_brings_target_to_viewport():
    """With offset (0, oy), a child at layout y=Y renders at screen y=Y-oy.
    This is the assumption Menu's scroll policy depends on. If _do_draw
    ever stops following this convention, every test above passes but
    rendering breaks — so encode the convention explicitly.
    """
    c = make_container(w=240, h=200, content_height=400)
    c.scroll((0, 80))
    child_box = Box.xywh(0, 240, 240, 40)

    off_real_box = c.box.norm().deoffset(c.offset)
    crb = child_box.offset(off_real_box.topleft)

    assert crb.rect == (0, 160, 240, 200)