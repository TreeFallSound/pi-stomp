"""
Unit tests for paint-context drawing logic:
  - Box.contains
  - Widget._draw_erase (safe-interior vs full-frame erase)
  - ContainerWidget.propagate_dirty scroll-offset translation
  - Relative-coord API contract
  - SDL clip containment (formerly slow-path scissor)
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


def _container(w=100, h=100, outline_radius=None, **kwargs):
    box = Box(0, 0, w, h)
    return ContainerWidget(box=box, outline_radius=outline_radius, **kwargs)


def _surface(w, h, color=(255, 255, 255), alpha=False):
    flags = pygame.SRCALPHA if alpha else 0
    surf = pygame.Surface((w, h), flags)
    surf.fill(color)
    return surf


# ---------------------------------------------------------------------------
# Box.contains
# ---------------------------------------------------------------------------


class TestBoxContains:
    def test_identical_boxes(self):
        b = Box(10, 10, 50, 50)
        assert b.contains(b)

    def test_inner_fully_inside(self):
        outer = Box(0, 0, 100, 100)
        inner = Box(10, 10, 90, 90)
        assert outer.contains(inner)

    def test_touching_edge_is_contained(self):
        outer = Box(0, 0, 100, 100)
        edge = Box(0, 0, 100, 50)
        assert outer.contains(edge)

    def test_partial_overlap_is_not_contained(self):
        a = Box(0, 0, 60, 60)
        b = Box(40, 40, 100, 100)
        assert not a.contains(b)

    def test_larger_box_not_contained(self):
        inner = Box(10, 10, 90, 90)
        outer = Box(0, 0, 100, 100)
        assert not inner.contains(outer)

    def test_empty_box_contained(self):
        outer = Box(0, 0, 100, 100)
        empty = Box(50, 50, 50, 50)
        assert outer.contains(empty)


# ---------------------------------------------------------------------------
# Widget._draw_erase
# ---------------------------------------------------------------------------


class TestDrawErase:
    """_draw_erase erases with a plain rect when the dirty region fits in the
    safe interior; falls back to a rounded rect when clip == bounds."""

    def _erase_and_read(self, clip, frame, outline_radius=None):
        surf = _surface(100, 100, (255, 255, 255))
        ctx = PaintContext(surf, clip, frame=frame)

        w = Widget(box=frame)
        w.outline_radius = outline_radius
        w.bkgnd_color = (0, 0, 0)

        w._draw_erase(ctx)
        return surf

    def test_no_radius_erases_only_clip(self):
        frame = Box(0, 0, 100, 100)
        clip = Box(10, 10, 50, 50)
        surf = self._erase_and_read(clip, frame, outline_radius=None)
        assert surf.get_at((20, 20))[:3] == (0, 0, 0)
        assert surf.get_at((80, 80))[:3] == (255, 255, 255)

    def test_radius_safe_interior_erases_only_clip(self):
        frame = Box(0, 0, 100, 100)
        clip = Box(20, 20, 80, 80)
        surf = self._erase_and_read(clip, frame, outline_radius=10)
        assert surf.get_at((50, 50))[:3] == (0, 0, 0)
        assert surf.get_at((5, 5))[:3] == (255, 255, 255)

    def test_radius_partial_clip_erases_only_intersection(self):
        frame = Box(0, 0, 100, 100)
        clip = Box(0, 0, 20, 20)
        surf = self._erase_and_read(clip, frame, outline_radius=10)
        assert surf.get_at((10, 10))[:3] == (0, 0, 0)
        assert surf.get_at((50, 50))[:3] == (255, 255, 255)

    def test_radius_full_frame_uses_rounded_rectangle(self):
        frame = Box(0, 0, 100, 100)
        surf = self._erase_and_read(frame, frame, outline_radius=10)
        assert surf.get_at((50, 50))[:3] == (0, 0, 0)
        # Absolute corner pixel NOT erased (rounded rect leaves it)
        assert surf.get_at((0, 0))[:3] == (255, 255, 255)


# ---------------------------------------------------------------------------
# propagate_dirty scroll offset
# ---------------------------------------------------------------------------


class TestPropagateDirtyScrollOffset:
    def test_no_scroll_translates_by_box_position(self):
        received = []

        class CapturingParent(Widget):
            def propagate_dirty(self, clip):
                received.append(clip)

        parent = CapturingParent(box=Box(0, 0, 200, 200))
        c = _container(w=100, h=100)
        c.box = Box(20, 30, 120, 130)
        c.parent = parent

        c.propagate_dirty(Box(10, 10, 50, 50))

        assert len(received) == 1
        assert received[0] == Box(30, 40, 70, 80)

    def test_scroll_offset_shifts_propagated_clip(self):
        received = []

        class CapturingParent(Widget):
            def propagate_dirty(self, clip):
                received.append(clip)

        parent = CapturingParent(box=Box(0, 0, 200, 200))
        c = _container(w=100, h=100)
        c.box = Box(20, 30, 120, 130)
        c.parent = parent
        c.offset = (5, 10)

        c.propagate_dirty(Box(10, 10, 50, 50))

        assert len(received) == 1
        assert received[0] == Box(25, 30, 65, 70)


# ---------------------------------------------------------------------------
# Relative-coordinate API contract
# ---------------------------------------------------------------------------


class _RelDrawWidget(Widget):
    def _draw(self, ctx):
        ctx.fill((255, 255, 255))
        ctx.draw_rectangle(Box(0, 0, 1, 1), fill=(255, 0, 0))
        ctx.draw_rectangle(Box(ctx.width - 1, ctx.height - 1, ctx.width, ctx.height), fill=(0, 255, 0))


class TestRelativeCoords:
    @pytest.mark.parametrize(
        "frame",
        [
            Box(0, 0, 20, 20),
            Box(50, 30, 70, 50),
            Box(99, 99, 119, 119),
        ],
    )
    def test_origin_marker_lands_at_frame_topleft(self, frame):
        surf = _surface(200, 200, (0, 0, 0))
        ctx = PaintContext(surf, Box(0, 0, 200, 200))

        w = _RelDrawWidget(box=frame)
        w.bkgnd_color = (0, 0, 0)
        w.fgnd_color = (255, 255, 255)
        w.do_draw(ctx, frame)

        assert surf.get_at(frame.topleft)[:3] == (255, 0, 0)
        far = (frame.x1 - 1, frame.y1 - 1)
        if 0 <= far[0] < 200 and 0 <= far[1] < 200:
            assert surf.get_at(far)[:3] == (0, 255, 0)
        if frame.x0 > 0:
            assert surf.get_at((frame.x0 - 1, frame.y0))[:3] == (0, 0, 0)


# ---------------------------------------------------------------------------
# SDL clip containment (replaces former slow-path BufferPool scissor)
# ---------------------------------------------------------------------------


class _SloppyWidget(Widget):
    """Intentionally draws past its own frame to test that the SDL clip
    (set by PaintContext.painting()) discards out-of-clip pixels."""

    def _draw(self, ctx):
        ctx.draw_rectangle(
            Box(-10, -10, ctx.width + 10, ctx.height + 10),
            fill=(255, 0, 0),
        )


class TestSloppyDrawContainment:
    def test_sdl_clip_scissors_oversized_draw(self):
        surf = _surface(200, 200, (0, 0, 0), alpha=True)
        # Clip strictly smaller than frame: anything outside clip must drop.
        frame = Box(50, 50, 150, 150)
        clip = Box(60, 60, 140, 140)
        ctx = PaintContext(surf, clip)

        w = _SloppyWidget(box=frame)
        w.bkgnd_color = (0, 0, 0, 0)
        w.fgnd_color = (255, 255, 255)
        w.do_draw(ctx, frame)

        # Inside clip: red
        assert surf.get_at((100, 100))[:3] == (255, 0, 0)

        # Inside frame, outside clip: SDL clip dropped it
        assert surf.get_at((55, 100))[:3] == (0, 0, 0)
        assert surf.get_at((145, 100))[:3] == (0, 0, 0)
        assert surf.get_at((100, 55))[:3] == (0, 0, 0)

        # Well outside frame: untouched
        assert surf.get_at((10, 10))[:3] == (0, 0, 0)
        assert surf.get_at((190, 190))[:3] == (0, 0, 0)
