"""
Unit tests for virtual container (JIT paint) behavior.

A ContainerWidget(virtual=True, content_height=N) keeps a "tall" backing surface
sized to N pixels.  Only children whose boxes intersect the current viewport
are painted; others are marked dirty and deferred until they scroll into view.

Contracts verified here:
  - Tall surface creation
  - refresh() gates on viewport: visible → painted, off-screen → dirty
  - Widget.refresh() marks dirty when off-screen; paints when on-screen
  - scroll() paints dirty/unpainted children that scroll into view
  - scroll() blits the correct tall-surface slice (pixel-level check)
  - set_selected + scroll_into_view ordering (mutation before blit)
  - Dirty-state transitions: never-painted → clean → dirty → clean
"""

import pytest
import pygame

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
    content_h = n * item_h
    box = Box.xywh(0, 0, VIEWPORT_W, viewport_h)
    return ContainerWidget(box=box, virtual=True, content_height=content_h)


def _pix(surf, xy):
    return tuple(surf.get_at(xy))[:3]


class _ColorWidget(Widget):
    def __init__(self, color, **kwargs):
        self.color = color
        super().__init__(**kwargs)

    def _draw(self, ctx):
        ctx.fill(self.color)


def _attach_items(container, n=N_ITEMS, item_h=ITEM_H):
    items = []
    for i in range(n):
        color = (i * 40, 0, 255 - i * 40)
        w = _ColorWidget(color=color, box=Box.xywh(0, i * item_h, VIEWPORT_W, item_h), parent=container)
        items.append((w, color))
    return items


# ---------------------------------------------------------------------------
# 1. Tall surface creation
# ---------------------------------------------------------------------------


class TestVirtualImageSize:
    def test_surface_height_is_content_height(self):
        c = _virtual_container()
        assert c.surface is not None
        assert c.surface.get_height() == N_ITEMS * ITEM_H

    def test_surface_width_matches_box(self):
        c = _virtual_container()
        assert c.surface is not None
        assert c.surface.get_width() == VIEWPORT_W

    def test_non_virtual_surface_matches_box(self):
        box = Box.xywh(0, 0, VIEWPORT_W, VIEWPORT_H)
        c = ContainerWidget(box=box)
        assert c.surface is not None
        assert c.surface.get_height() == VIEWPORT_H


# ---------------------------------------------------------------------------
# 2. refresh() — viewport gating
# ---------------------------------------------------------------------------


class TestRefreshViewportGating:
    def test_visible_items_painted_after_refresh(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        visible_count = VIEWPORT_H // ITEM_H
        for i, (w, _) in enumerate(items):
            if i < visible_count:
                assert w._painted, f"item {i} should be painted"
                assert not w._dirty, f"item {i} should not be dirty"
            else:
                assert w._dirty, f"item {i} should be marked dirty"
                assert not w._painted, f"item {i} should not be painted yet"

    def test_visible_item_pixels_land_in_tall_surface(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        visible_count = VIEWPORT_H // ITEM_H
        for i, (w, color) in enumerate(items[:visible_count]):
            sample_y = i * ITEM_H + ITEM_H // 2
            assert _pix(c.surface, (VIEWPORT_W // 2, sample_y)) == color, (
                f"item {i} color {color} not found at tall-surface y={sample_y}"
            )

    def test_off_screen_item_pixels_not_in_surface_background(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        for i, (w, color) in enumerate(items[VIEWPORT_H // ITEM_H :], start=VIEWPORT_H // ITEM_H):
            sample_y = i * ITEM_H + ITEM_H // 2
            assert _pix(c.surface, (VIEWPORT_W // 2, sample_y)) != color, (
                f"item {i} color leaked into tall surface before scroll"
            )


# ---------------------------------------------------------------------------
# 3. Widget.refresh() — per-widget dirty / paint decision
# ---------------------------------------------------------------------------


class TestWidgetRefreshJIT:
    def test_off_screen_widget_refresh_marks_dirty(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        off_screen = items[N_ITEMS - 1][0]
        assert not off_screen._painted

        off_screen.refresh()

        assert off_screen._dirty
        assert not off_screen._painted

    def test_on_screen_widget_refresh_paints(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        on_screen = items[0][0]
        on_screen._painted = False
        on_screen._dirty = True

        on_screen.refresh()

        assert on_screen._painted
        assert not on_screen._dirty

    def test_off_screen_refresh_does_not_paint_pixels(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        idx = N_ITEMS - 1
        w, color = items[idx]
        sample_y = idx * ITEM_H + ITEM_H // 2

        before = _pix(c.surface, (VIEWPORT_W // 2, sample_y))
        w.refresh()
        after = _pix(c.surface, (VIEWPORT_W // 2, sample_y))

        assert before == after


# ---------------------------------------------------------------------------
# 4. scroll() — paints newly visible dirty children
# ---------------------------------------------------------------------------


class TestScrollPaintsNewlyVisible:
    def test_scroll_paints_dirty_children(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        c.scroll((0, VIEWPORT_H))

        newly_visible_start = VIEWPORT_H // ITEM_H
        for i, (w, _) in enumerate(items):
            if i >= newly_visible_start:
                assert w._painted, f"item {i} should be painted after scroll"
                assert not w._dirty, f"item {i} should be clean after scroll"

    def test_scroll_paints_correct_pixels_in_tall_surface(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        c.scroll((0, VIEWPORT_H))

        for i, (w, color) in enumerate(items[VIEWPORT_H // ITEM_H :], start=VIEWPORT_H // ITEM_H):
            sample_y = i * ITEM_H + ITEM_H // 2
            assert _pix(c.surface, (VIEWPORT_W // 2, sample_y)) == color, (
                f"item {i} color {color} not found at tall-surface y={sample_y} after scroll"
            )

    def test_scroll_skips_already_clean_children(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        draw_counts = {i: 0 for i in range(N_ITEMS)}
        for i, (w, _) in enumerate(items):

            def make_counter(orig, item_i):
                def _draw_counted(ctx):
                    draw_counts[item_i] += 1
                    orig(ctx)

                return _draw_counted

            w._draw = make_counter(w._draw, i)

        c.scroll((0, VIEWPORT_H))

        newly_visible_start = VIEWPORT_H // ITEM_H
        for i in range(newly_visible_start, N_ITEMS):
            assert draw_counts[i] == 1, f"item {i} should have been drawn once"
        for i in range(newly_visible_start):
            assert draw_counts[i] == 0, f"item {i} should not have been redrawn"


# ---------------------------------------------------------------------------
# 5. do_draw blits the correct tall-surface slice into the parent
# ---------------------------------------------------------------------------


def _parent_ctx(w=VIEWPORT_W, h=VIEWPORT_H, fill=(128, 128, 128)):
    surf = pygame.Surface((w, h))
    surf.fill(fill)
    ctx = PaintContext(surf, Box.xywh(0, 0, w, h))
    return surf, ctx


class TestDoDrawBlit:
    def test_do_draw_shows_scrolled_content_in_parent(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()
        c.scroll((0, VIEWPORT_H))

        parent_surf, ctx = _parent_ctx()
        c.do_draw(ctx, Box.xywh(0, 0, VIEWPORT_W, VIEWPORT_H))

        _, item3_color = items[VIEWPORT_H // ITEM_H]
        top_pixel = _pix(parent_surf, (VIEWPORT_W // 2, ITEM_H // 2))
        assert top_pixel == item3_color, f"Expected item3 color {item3_color} at top of parent, got {top_pixel}"

        _, item0_color = items[0]
        assert top_pixel != item0_color

    def test_do_draw_no_scroll_shows_first_items(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        parent_surf, ctx = _parent_ctx()
        c.do_draw(ctx, Box.xywh(0, 0, VIEWPORT_W, VIEWPORT_H))

        _, item0_color = items[0]
        top_pixel = _pix(parent_surf, (VIEWPORT_W // 2, ITEM_H // 2))
        assert top_pixel == item0_color


# ---------------------------------------------------------------------------
# 5b. Scroll-by-blit: scrolling back over already-painted children must not
#     re-invoke child _draw, and do_draw on a virtual container is pure blit.
# ---------------------------------------------------------------------------


class TestScrollByBlitNoRebuild:
    def _paint_all_and_spy(self, c, items):
        c.refresh()
        c.scroll((0, (N_ITEMS - VIEWPORT_H // ITEM_H) * ITEM_H))
        c.scroll((0, 0))

        for w, _ in items:
            assert w._painted and not w._dirty

        counts = {i: 0 for i in range(len(items))}
        for i, (w, _) in enumerate(items):

            def make_spy(orig, idx):
                def _spy(ctx):
                    counts[idx] += 1
                    orig(ctx)

                return _spy

            w._draw = make_spy(w._draw, i)

        return counts

    def test_scroll_over_painted_children_does_no_child_draw(self):
        c = _virtual_container()
        items = _attach_items(c)
        counts = self._paint_all_and_spy(c, items)

        c.scroll((0, VIEWPORT_H))

        assert all(v == 0 for v in counts.values()), f"expected zero child redraws on scroll-over-painted, got {counts}"

    def test_do_draw_after_scroll_is_pure_blit(self):
        c = _virtual_container()
        items = _attach_items(c)
        counts = self._paint_all_and_spy(c, items)

        c.scroll((0, VIEWPORT_H))
        parent_surf, ctx = _parent_ctx()
        c.do_draw(ctx, Box.xywh(0, 0, VIEWPORT_W, VIEWPORT_H))

        assert all(v == 0 for v in counts.values()), f"do_draw on virtual must not invoke child _draw; got {counts}"

        _, item3_color = items[VIEWPORT_H // ITEM_H]
        top_pixel = _pix(parent_surf, (VIEWPORT_W // 2, ITEM_H // 2))
        assert top_pixel == item3_color


# ---------------------------------------------------------------------------
# 6. Pixel-level blit: scroll emits the right slice via propagate_dirty
# ---------------------------------------------------------------------------


class TestScrollBlit:
    def test_viewport_slice_corresponds_to_scroll_offset(self):
        received = []

        class CapturingParent(Widget):
            def propagate_dirty(self, clip):
                received.append(clip.copy())

        c = _virtual_container()
        _attach_items(c)
        c.refresh()

        c.box = Box.xywh(10, 5, VIEWPORT_W, VIEWPORT_H)
        c.parent = CapturingParent(box=Box.xywh(0, 0, 200, 200))
        c.scroll((0, VIEWPORT_H))

        assert received
        last = received[-1]
        expected = Box.xywh(10, 5, VIEWPORT_W, VIEWPORT_H)
        assert last == expected


# ---------------------------------------------------------------------------
# 7. set_selected + scroll_into_view ordering
# ---------------------------------------------------------------------------


class TestSelectionScrollOrdering:
    def test_selected_state_visible_after_scroll(self):
        c = _virtual_container()
        items = _attach_items(c)
        c.refresh()

        last_w, _ = items[N_ITEMS - 1]
        drawn_selected = []
        orig_draw = last_w._draw

        def _spy_draw(ctx):
            drawn_selected.append(last_w.selected)
            orig_draw(ctx)

        last_w._draw = _spy_draw
        last_w.selectable = True
        last_w.selected = True

        scrolled = last_w.scroll_into_view()
        if scrolled:
            assert drawn_selected
            assert drawn_selected[-1] is True


# ---------------------------------------------------------------------------
# 8. Dirty-state transitions
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
        w._dirty = True
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
        c.scroll((0, (N_ITEMS - 1) * ITEM_H))
        assert w._painted
        assert not w._dirty


# ---------------------------------------------------------------------------
# 9. Menu snapshot — full PanelStack → LCD render path
# ---------------------------------------------------------------------------


@pytest.fixture
def ui_config():
    import os
    from uilib.config import Config

    Config._instance = None
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    Config(os.path.join(project_root, "ui", "config.json"))


class TestMenuSnapshot:
    _ITEM_NAMES = [f"Item {i}" for i in range(8)]

    def _make_stack(self, fake_lcd):
        from uilib.panel import PanelStack

        stack = PanelStack(fake_lcd)
        fake_lcd.flush_callback = stack.poll_updates
        return stack

    def _make_menu(self, stack):
        from uilib.menu import Menu

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

        for _ in range(len(menu.sel_list) - 1):
            menu.sel_next()

        snapshot("scrolled_to_last")

    def test_scroll_back_and_forth(self, fake_lcd, snapshot, ui_config):
        stack = self._make_stack(fake_lcd)
        menu = self._make_menu(stack)

        for _ in range(4):
            menu.sel_next()
        snapshot()
        menu.sel_next()
        snapshot()
        menu.sel_next()
        snapshot()
        menu.sel_prev()
        snapshot()
        menu.sel_prev()
        snapshot()
