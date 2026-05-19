"""
Unit tests for virtual container (JIT paint) behavior.

A ContainerWidget(virtual=True, content_height=N) keeps a "tall" backing image
sized to N pixels.  Only children whose boxes intersect the current viewport
are painted; others are marked dirty and deferred until they scroll into view.

Contracts verified here:
  - Tall image creation
  - refresh() gates on viewport: visible → painted, off-screen → dirty
  - Widget.refresh() marks dirty when off-screen; paints when on-screen
  - scroll() paints dirty/unpainted children that scroll into view
  - scroll() blits the correct tall-image slice (pixel-level check)
  - set_selected + scroll_into_view ordering (mutation before blit)
  - Dirty-state transitions: never-painted → clean → dirty → clean
"""

import pytest
from PIL import Image, ImageDraw

from uilib.box import Box
from uilib.paint import PaintContext
from uilib.container import ContainerWidget
from uilib.widget import Widget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VIEWPORT_W = 100
VIEWPORT_H = 60  # shows 3 rows of 20px each
ITEM_H = 20
N_ITEMS = 6  # 6 rows → content_height = 120


def _virtual_container(n=N_ITEMS, item_h=ITEM_H, viewport_h=VIEWPORT_H):
    """Return a virtual container (no parent) ready to hold items."""
    content_h = n * item_h
    box = Box.xywh(0, 0, VIEWPORT_W, viewport_h)
    return ContainerWidget(box=box, virtual=True, content_height=content_h)


class _ColorWidget(Widget):
    """Fills its frame with a solid color so we can verify pixel placement."""

    def __init__(self, color, **kwargs):
        self.color = color
        super().__init__(**kwargs)

    def _draw(self, ctx):
        ctx.fill(self.color)


def _attach_items(container, n=N_ITEMS, item_h=ITEM_H):
    """Attach n items with distinct colors.  Returns list of (widget, color)."""
    items = []
    for i in range(n):
        color = (i * 40, 0, 255 - i * 40)
        w = _ColorWidget(color=color, box=Box.xywh(0, i * item_h, VIEWPORT_W, item_h), parent=container)
        items.append((w, color))
    return items


# ---------------------------------------------------------------------------
# 1. Tall image creation
# ---------------------------------------------------------------------------


class TestVirtualImageSize:
    def test_image_height_is_content_height(self):
        c = _virtual_container()
        assert c.image.height == N_ITEMS * ITEM_H

    def test_image_width_matches_box(self):
        c = _virtual_container()
        assert c.image.width == VIEWPORT_W

    def test_non_virtual_image_matches_box(self):
        box = Box.xywh(0, 0, VIEWPORT_W, VIEWPORT_H)
        c = ContainerWidget(box=box)
        assert c.image.height == VIEWPORT_H


# ---------------------------------------------------------------------------
# 2. refresh() — viewport gating
# ---------------------------------------------------------------------------


class TestRefreshViewportGating:
    def test_visible_items_painted_after_refresh(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        # Initial viewport is y=0..VIEWPORT_H: items 0..2 (rows 0,1,2)
        visible_count = VIEWPORT_H // ITEM_H
        for i, (w, _) in enumerate(items):
            if i < visible_count:
                assert w._painted, f"item {i} should be painted"
                assert not w._dirty, f"item {i} should not be dirty"
            else:
                assert w._dirty, f"item {i} should be marked dirty"
                assert not w._painted, f"item {i} should not be painted yet"

    def test_visible_item_pixels_land_in_tall_image(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        # Each visible item should have its color in the tall image
        visible_count = VIEWPORT_H // ITEM_H
        for i, (w, color) in enumerate(items[:visible_count]):
            sample_y = i * ITEM_H + ITEM_H // 2
            pixel = c.image.getpixel((VIEWPORT_W // 2, sample_y))
            assert pixel[:3] == color[:3], f"item {i} color {color} not found at tall-image y={sample_y}"

    def test_off_screen_item_pixels_not_in_image_background(self):
        """Off-screen items are never painted; their rows stay at the container
        background color (default black) until they scroll into view."""
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        # Items beyond viewport_h are unpainted → black background
        for i, (w, color) in enumerate(items[VIEWPORT_H // ITEM_H :], start=VIEWPORT_H // ITEM_H):
            sample_y = i * ITEM_H + ITEM_H // 2
            pixel = c.image.getpixel((VIEWPORT_W // 2, sample_y))
            # Should still be default background, not the item's color
            assert pixel[:3] != color[:3], f"item {i} color leaked into tall image before scroll"


# ---------------------------------------------------------------------------
# 3. Widget.refresh() — per-widget dirty / paint decision
# ---------------------------------------------------------------------------


class TestWidgetRefreshJIT:
    def test_off_screen_widget_refresh_marks_dirty(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()  # initial paint of visible items

        off_screen = items[N_ITEMS - 1][0]  # last item, far off-screen
        assert not off_screen._painted

        off_screen.refresh()

        assert off_screen._dirty
        assert not off_screen._painted  # still not painted

    def test_on_screen_widget_refresh_paints(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()  # initial paint

        on_screen = items[0][0]
        on_screen._painted = False  # simulate needing a redraw
        on_screen._dirty = True

        on_screen.refresh()

        assert on_screen._painted
        assert not on_screen._dirty

    def test_off_screen_refresh_does_not_paint_pixels(self):
        """An off-screen widget.refresh() must not change tall-image pixels."""
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        idx = N_ITEMS - 1
        w, color = items[idx]
        sample_y = idx * ITEM_H + ITEM_H // 2

        # Record pixel before the off-screen refresh
        before = c.image.getpixel((VIEWPORT_W // 2, sample_y))
        w.refresh()
        after = c.image.getpixel((VIEWPORT_W // 2, sample_y))

        assert before == after, "off-screen refresh must not write pixels"


# ---------------------------------------------------------------------------
# 4. scroll() — paints newly visible dirty children
# ---------------------------------------------------------------------------


class TestScrollPaintsNewlyVisible:
    def test_scroll_paints_dirty_children(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        # Scroll down by VIEWPORT_H: items 3..5 enter the viewport
        c.scroll((0, VIEWPORT_H))

        newly_visible_start = VIEWPORT_H // ITEM_H
        for i, (w, _) in enumerate(items):
            if i >= newly_visible_start:
                assert w._painted, f"item {i} should be painted after scroll"
                assert not w._dirty, f"item {i} should be clean after scroll"

    def test_scroll_paints_correct_pixels_in_tall_image(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        c.scroll((0, VIEWPORT_H))

        # Items 3..5 should now have their colors in the tall image
        for i, (w, color) in enumerate(items[VIEWPORT_H // ITEM_H :], start=VIEWPORT_H // ITEM_H):
            sample_y = i * ITEM_H + ITEM_H // 2
            pixel = c.image.getpixel((VIEWPORT_W // 2, sample_y))
            assert pixel[:3] == color[:3], f"item {i} color {color} not found at tall-image y={sample_y} after scroll"

    def test_scroll_skips_already_clean_children(self):
        """Children that are painted and clean must not be redrawn on scroll."""
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        draw_counts = {i: 0 for i in range(N_ITEMS)}
        originals = {}
        for i, (w, _) in enumerate(items):
            originals[i] = w._draw
            idx = i

            def make_counter(orig, item_i):
                def _draw_counted(ctx):
                    draw_counts[item_i] += 1
                    orig(ctx)

                return _draw_counted

            w._draw = make_counter(w._draw, i)

        # Scroll to show items 3..5 (items 0..2 are still technically overlapping
        # the prior viewport's bottom row, but items 0..2 are clean → skip)
        c.scroll((0, VIEWPORT_H))

        # Dirty items (3..5) should have been drawn exactly once
        newly_visible_start = VIEWPORT_H // ITEM_H
        for i in range(newly_visible_start, N_ITEMS):
            assert draw_counts[i] == 1, f"item {i} should have been drawn once"
        # Clean items (0..2) must not have been redrawn
        for i in range(newly_visible_start):
            assert draw_counts[i] == 0, f"item {i} should not have been redrawn"


# ---------------------------------------------------------------------------
# 5. do_draw blits the correct tall-image slice into the parent
# ---------------------------------------------------------------------------


class TestDoDrawBlit:
    """After scroll(y=N), do_draw must composite the slice starting at y=N in
    the tall image into the parent surface — not the slice at y=0."""

    def test_do_draw_shows_scrolled_content_in_parent(self):
        from uilib.paint import BufferPool

        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()
        c.scroll((0, VIEWPORT_H))  # items 3..5 now in viewport

        # Build a parent image and call do_draw on the container
        parent_img = Image.new("RGB", (VIEWPORT_W, VIEWPORT_H), (128, 128, 128))
        pool = BufferPool((VIEWPORT_W, VIEWPORT_H))
        ctx = PaintContext(parent_img, ImageDraw.Draw(parent_img), Box.xywh(0, 0, VIEWPORT_W, VIEWPORT_H), pool)
        container_frame = Box.xywh(0, 0, VIEWPORT_W, VIEWPORT_H)

        c.do_draw(ctx, container_frame)

        # Item 3 occupies row 0 of the viewport after scroll(VIEWPORT_H).
        # Its color must appear at the top of the parent image.
        _, item3_color = items[VIEWPORT_H // ITEM_H]
        top_pixel = parent_img.getpixel((VIEWPORT_W // 2, ITEM_H // 2))
        assert top_pixel[:3] == item3_color[:3], f"Expected item3 color {item3_color} at top of parent, got {top_pixel}"

        # Item 0 must NOT appear at the top of the parent image.
        _, item0_color = items[0]
        assert top_pixel[:3] != item0_color[:3], "Item 0 must not appear at top of parent after scroll"

    def test_do_draw_no_scroll_shows_first_items(self):
        from uilib.paint import BufferPool

        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()  # no scroll — viewport is at y=0

        parent_img = Image.new("RGB", (VIEWPORT_W, VIEWPORT_H), (128, 128, 128))
        pool = BufferPool((VIEWPORT_W, VIEWPORT_H))
        ctx = PaintContext(parent_img, ImageDraw.Draw(parent_img), Box.xywh(0, 0, VIEWPORT_W, VIEWPORT_H), pool)

        c.do_draw(ctx, Box.xywh(0, 0, VIEWPORT_W, VIEWPORT_H))

        _, item0_color = items[0]
        top_pixel = parent_img.getpixel((VIEWPORT_W // 2, ITEM_H // 2))
        assert top_pixel[:3] == item0_color[:3], (
            f"Expected item0 color {item0_color} at top of parent (no scroll), got {top_pixel}"
        )


# ---------------------------------------------------------------------------
# 5b. Scroll-by-blit: scrolling back over already-painted children
#     must not re-invoke child _draw — neither in scroll() nor in the
#     subsequent do_draw on a parent surface.  do_draw on a virtual
#     container is pure cache-blit.
# ---------------------------------------------------------------------------


class TestScrollByBlitNoRebuild:
    def _paint_all_and_spy(self, c, items):
        """Paint every item into the cache, then install per-item _draw spies
        and return the counters dict.  After this, all items are _painted and
        not _dirty, so subsequent paints would be redundant."""
        c.refresh()                            # paints items 0..2
        c.scroll((0, (N_ITEMS - VIEWPORT_H // ITEM_H) * ITEM_H))  # paints items 3..5
        c.scroll((0, 0))                       # back to top; everything cached

        # Sanity: every item must be painted and clean before the spy goes in.
        for w, _ in items:
            assert w._painted and not w._dirty

        counts = {i: 0 for i in range(len(items))}
        for i, (w, _) in enumerate(items):
            orig = w._draw

            def make_spy(orig, idx):
                def _spy(ctx):
                    counts[idx] += 1
                    orig(ctx)
                return _spy

            w._draw = make_spy(orig, i)

        return counts

    def test_scroll_over_painted_children_does_no_child_draw(self):
        """scroll() to a region whose children are all cached+clean must not
        invoke any child _draw."""
        c = _virtual_container()
        items = _attach_items(c)
        counts = self._paint_all_and_spy(c, items)

        c.scroll((0, VIEWPORT_H))  # items 3..5 — all already painted+clean

        assert all(v == 0 for v in counts.values()), (
            f"expected zero child redraws on scroll-over-painted, got {counts}"
        )

    def test_do_draw_after_scroll_is_pure_blit(self):
        """After scroll, do_draw on a parent surface must be a pure cache blit:
        no child _draw invocations.  Pixels must still match the cached state."""
        from uilib.paint import BufferPool

        c = _virtual_container()
        items = _attach_items(c)
        counts = self._paint_all_and_spy(c, items)

        # Scroll to a previously-painted region, then have a "parent" composite us.
        c.scroll((0, VIEWPORT_H))
        parent_img = Image.new("RGB", (VIEWPORT_W, VIEWPORT_H), (128, 128, 128))
        pool = BufferPool((VIEWPORT_W, VIEWPORT_H))
        ctx = PaintContext(
            parent_img,
            ImageDraw.Draw(parent_img),
            Box.xywh(0, 0, VIEWPORT_W, VIEWPORT_H),
            pool,
        )
        c.do_draw(ctx, Box.xywh(0, 0, VIEWPORT_W, VIEWPORT_H))

        assert all(v == 0 for v in counts.values()), (
            f"do_draw on virtual must not invoke child _draw; got {counts}"
        )

        # Item 3 (first visible row after scroll) should appear at the top.
        _, item3_color = items[VIEWPORT_H // ITEM_H]
        top_pixel = parent_img.getpixel((VIEWPORT_W // 2, ITEM_H // 2))
        assert top_pixel[:3] == item3_color[:3]


# ---------------------------------------------------------------------------
# 6. Pixel-level blit: scroll shows the right slice
# ---------------------------------------------------------------------------


class TestScrollBlit:
    def _setup_and_scroll(self, scroll_y):
        """Return (container, items) after refresh + scroll."""
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()
        c.scroll((0, scroll_y))
        return c, items

    def test_viewport_slice_corresponds_to_scroll_offset(self):
        """After scroll(y=VIEWPORT_H), the visible viewport starts at VIEWPORT_H
        in the tall image.  The propagate_dirty call must emit the correct slice."""
        received = []

        class CapturingParent(Widget):
            def propagate_dirty(self, clip):
                received.append(clip.copy())

        c = _virtual_container()
        _attach_items(c)
        c.refresh()

        # Attach a capturing parent and scroll
        c.box = Box.xywh(10, 5, VIEWPORT_W, VIEWPORT_H)
        c.parent = CapturingParent(box=Box.xywh(0, 0, 200, 200))
        c.scroll((0, VIEWPORT_H))

        assert received, "scroll() must call propagate_dirty"
        last = received[-1]
        # propagate_dirty converts viewport content coords → parent-space coords:
        #   content viewport Box(0, VIEWPORT_H, W, 2*VIEWPORT_H)
        #   deoffset((0, VIEWPORT_H)) → Box(0, 0, W, VIEWPORT_H)   (viewport-relative)
        #   offset(box.topleft=(10,5)) → Box(10, 5, W+10, VIEWPORT_H+5)  (parent-space)
        expected = Box.xywh(10, 5, VIEWPORT_W, VIEWPORT_H)
        assert last == expected, f"Expected parent-space clip {expected}, got {last}"


# ---------------------------------------------------------------------------
# 6. set_selected + scroll_into_view ordering
# ---------------------------------------------------------------------------


class TestSelectionScrollOrdering:
    def test_selected_state_visible_after_scroll(self):
        """Mutate state → mark dirty → scroll → on-scroll paint must capture
        the post-mutation state (selected=True visually)."""
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        # Track what color each draw sees for item[N_ITEMS-1]
        last_w, _ = items[N_ITEMS - 1]
        drawn_selected = []

        orig_draw = last_w._draw

        def _spy_draw(ctx):
            drawn_selected.append(last_w.selected)
            orig_draw(ctx)

        last_w._draw = _spy_draw
        last_w.selectable = True
        last_w.selected = True  # mutate state

        # scroll_into_view triggers scroll(), which should paint the dirty widget
        scrolled = last_w.scroll_into_view()

        if scrolled:
            # Widget was off-screen and scroll happened → paint occurred via scroll()
            assert drawn_selected, "widget must have been painted during scroll"
            assert drawn_selected[-1] is True, "widget must be painted with selected=True (post-mutation state)"


# ---------------------------------------------------------------------------
# 7. Dirty-state transitions
# ---------------------------------------------------------------------------


class TestDirtyStateTransitions:
    def test_initial_state_never_painted(self):
        c = _virtual_container()
        items = _attach_items(c)

        for w, _ in items:
            assert not w._painted
            assert not w._dirty

    def test_after_refresh_visible_clean(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        visible_count = VIEWPORT_H // ITEM_H
        for w, _ in items[:visible_count]:
            assert w._painted and not w._dirty

    def test_after_refresh_off_screen_dirty(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        visible_count = VIEWPORT_H // ITEM_H
        for w, _ in items[visible_count:]:
            assert w._dirty and not w._painted

    def test_widget_refresh_on_screen_clears_dirty(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        w = items[0][0]
        w._dirty = True  # simulate state change

        w.refresh()

        assert w._painted
        assert not w._dirty

    def test_widget_refresh_off_screen_sets_dirty(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        w = items[N_ITEMS - 1][0]
        assert not w._painted

        w.refresh()

        assert w._dirty
        assert not w._painted

    def test_scroll_into_view_clears_dirty(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        w, _ = items[N_ITEMS - 1]
        assert w._dirty

        c.scroll((0, (N_ITEMS - 1) * ITEM_H))  # scroll last item into view

        assert w._painted
        assert not w._dirty


# ---------------------------------------------------------------------------
# 9. Menu snapshot — full PanelStack → LCD render path
# ---------------------------------------------------------------------------


@pytest.fixture
def ui_config():
    """Initialize the uilib Config singleton with the project's ui/config.json."""
    import os
    from uilib.config import Config

    # Reset singleton so it reinitialises cleanly for each test
    Config._instance = None
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    Config(os.path.join(project_root, "ui", "config.json"))


class TestMenuSnapshot:
    """Snapshot tests for a real Menu with virtual scrolling.

    These go through PanelStack → do_draw → LCD.update, so they cover the
    tall-image blit path that pixel-unit tests above can only approximate.
    Running with --snapshot-update regenerates the baselines.
    """

    _ITEM_NAMES = [f"Item {i}" for i in range(8)]

    def _make_stack(self, fake_lcd):
        from uilib.panel import PanelStack

        return PanelStack(fake_lcd)

    def _make_menu(self, stack):
        from uilib.menu import Menu

        # max_height forces virtual mode when total content exceeds it.
        # dismiss_option=True adds the back-arrow item (matches real-world usage).
        menu = Menu(
            items=[(name, None, None) for name in self._ITEM_NAMES],
            max_height=100,
            title="Test Menu",
            dismiss_option=True,
        )
        stack.push_panel(menu)
        return menu

    def test_initial_render(self, fake_lcd, snapshot, ui_config):
        stack = self._make_stack(fake_lcd)
        self._make_menu(stack)
        snapshot("initial")

    def test_scroll_shows_later_items(self, fake_lcd, snapshot, ui_config):
        stack = self._make_stack(fake_lcd)
        menu = self._make_menu(stack)
        snapshot("initial")

        # Advance to the last selectable item (includes the back arrow)
        for _ in range(len(menu.sel_list) - 1):
            menu.sel_next()

        snapshot("scrolled_to_last")

    def test_scroll_back_and_forth(self, fake_lcd, snapshot, ui_config):
        stack = self._make_stack(fake_lcd)
        menu = self._make_menu(stack)

        # 0 -> 4
        for _ in range(4):
            menu.sel_next()
        print(f"at 4: offset={menu.offset}")
        snapshot()
        # -> 5
        menu.sel_next()
        print(f"at 5: offset={menu.offset}")
        snapshot()
        # -> 6
        menu.sel_next()
        print(f"at 6: offset={menu.offset}")
        snapshot()
        # -> 5
        menu.sel_prev()
        print(f"back to 5: offset={menu.offset}")
        snapshot()
        # -> 4
        menu.sel_prev()
        print(f"back to 4: offset={menu.offset}")
        snapshot()
