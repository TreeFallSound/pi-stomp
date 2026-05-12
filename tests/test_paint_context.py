"""
Unit tests for paint-context drawing logic:
  - Box.contains
  - Widget._draw_erase (safe-interior vs full-frame erase)
  - ContainerWidget._do_draw clip expansion for rounded containers
  - ContainerWidget._propagate_dirty scroll-offset translation
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

def _container(w=100, h=100, outline_radius=None, **kwargs):
    box = Box(0, 0, w, h)
    c = ContainerWidget(box=box, outline_radius=outline_radius, **kwargs)
    return c


def _ctx(container, clip=None):
    if clip is None:
        clip = container.box.norm()
    return PaintContext(container.image, container.draw, clip)


def _painted_colors(image):
    """Return the set of distinct RGB tuples present in the image."""
    return set(image.getdata())


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
        edge = Box(0, 0, 100, 50)   # shares top/left/right edge
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
        empty = Box(50, 50, 50, 50)   # zero-area
        assert outer.contains(empty)


# ---------------------------------------------------------------------------
# Widget._draw_erase
# ---------------------------------------------------------------------------

class TestDrawErase:
    """_draw_erase erases with a plain rect when the dirty region fits in the
    safe interior; falls back to a full rounded_rectangle when it touches a
    corner."""

    def _erase_and_read(self, clip, frame, outline_radius=None):
        """Erase `frame` in a white 100×100 image using `clip` as the dirty
        region.  Returns the image so the caller can inspect pixels."""
        img = Image.new("RGB", (100, 100), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        ctx = PaintContext(img, draw, clip)

        w = Widget(box=frame)
        w.outline_radius = outline_radius
        w.bkgnd_color = (0, 0, 0)

        w._draw_erase(ctx, frame)
        return img

    def test_no_radius_erases_only_clip(self):
        frame = Box(0, 0, 100, 100)
        clip  = Box(10, 10, 50, 50)
        img   = self._erase_and_read(clip, frame, outline_radius=None)
        # Clipped region is black
        assert img.getpixel((20, 20)) == (0, 0, 0)
        # Outside clip stays white
        assert img.getpixel((80, 80)) == (255, 255, 255)

    def test_radius_safe_interior_erases_only_clip(self):
        """Dirty region inside the safe interior → plain rect erase."""
        frame = Box(0, 0, 100, 100)
        r     = 10
        # clip well inside the safe zone (r..100-r on each axis)
        clip  = Box(20, 20, 80, 80)
        img   = self._erase_and_read(clip, frame, outline_radius=r)
        assert img.getpixel((50, 50)) == (0, 0, 0)   # inside clip → erased
        assert img.getpixel((5, 5))   == (255, 255, 255)  # corner → untouched

    def test_radius_partial_clip_erases_only_intersection(self):
        """Partial clip on a rounded widget → plain rect erase of the intersection.
        Full-frame expansion for rounded shapes is ContainerWidget._do_draw's job,
        not _draw_erase's.  A leaf widget with outline_radius still gets a rect
        erase when the clip is smaller than the frame."""
        frame = Box(0, 0, 100, 100)
        r     = 10
        clip  = Box(0, 0, 20, 20)
        img   = self._erase_and_read(clip, frame, outline_radius=r)
        # Only the clipped region is erased
        assert img.getpixel((10, 10)) == (0, 0, 0)
        # Centre untouched — no full-frame expansion at this level
        assert img.getpixel((50, 50)) == (255, 255, 255)

    def test_radius_full_frame_uses_rounded_rectangle(self):
        """When clip == frame, always use rounded_rectangle (corners preserved)."""
        frame = Box(0, 0, 100, 100)
        r     = 10
        img   = self._erase_and_read(frame, frame, outline_radius=r)
        # Centre erased
        assert img.getpixel((50, 50)) == (0, 0, 0)
        # Absolute corner pixels NOT erased (rounded rect leaves them)
        assert img.getpixel((0, 0))   == (255, 255, 255)


# ---------------------------------------------------------------------------
# ContainerWidget._do_draw clip expansion
# ---------------------------------------------------------------------------

class TestContainerClipExpansion:
    """When a rounded container's dirty clip touches a corner, _do_draw must
    expand the clip to the full frame so that both erase and child-draws are
    consistent (no content left erased-but-not-redrawn)."""

    def _make_rounded_container(self, r=10):
        return _container(w=100, h=100, outline_radius=r)

    def test_no_radius_no_expansion(self):
        c = _container(outline_radius=None)
        # Paint a sentinel pixel in the top-left corner of the container image
        c.image.putpixel((5, 5), (255, 0, 0))

        # Dirty clip covers only the bottom-right area — does not include (5,5)
        clip  = Box(50, 50, 100, 100)
        frame = Box(0, 0, 100, 100)
        parent_img = Image.new("RGB", (100, 100), (128, 128, 128))
        parent_draw = ImageDraw.Draw(parent_img)
        ctx = PaintContext(parent_img, parent_draw, clip)

        c._do_draw(ctx, frame)
        # The sentinel pixel in container image should be unchanged (no expansion)
        assert c.image.getpixel((5, 5)) == (255, 0, 0)

    def test_radius_corner_clip_expands_to_full_frame(self):
        """A clip touching a corner should expand so all children get redrawn."""
        r = 10
        c = _container(w=100, h=100, outline_radius=r)

        # Add a child widget that tracks whether it was drawn
        drawn_frames = []
        class TrackingWidget(Widget):
            def _draw(self, ctx, frame):
                drawn_frames.append(frame.copy())

        child_box = Box(5, 5, 40, 20)   # in top-left — inside corner region
        child = TrackingWidget(box=child_box)
        child.attach(c)
        child.bkgnd_color = (0, 0, 0)
        child.fgnd_color = (255, 255, 255)

        # Dirty clip covers only the bottom-right, away from the child
        clip  = Box(60, 60, 100, 100)
        frame = Box(0, 0, 100, 100)
        parent_img = Image.new("RGB", (100, 100))
        ctx = PaintContext(parent_img, ImageDraw.Draw(parent_img), clip)

        c._do_draw(ctx, frame)

        # Child must have been drawn (clip was expanded to cover it)
        assert len(drawn_frames) == 1

    def test_radius_safe_interior_clip_does_not_expand(self):
        """A clip fully inside the safe interior should NOT trigger expansion."""
        r = 10
        c = _container(w=100, h=100, outline_radius=r)

        drawn_frames = []
        class TrackingWidget(Widget):
            def _draw(self, ctx, frame):
                drawn_frames.append(frame.copy())

        # Child is in top-left corner region
        child = TrackingWidget(box=Box(2, 2, 8, 8))
        child.attach(c)
        child.bkgnd_color = (0, 0, 0)
        child.fgnd_color = (255, 255, 255)

        # Dirty clip is fully in the safe interior (r..100-r)
        clip  = Box(20, 20, 80, 80)
        frame = Box(0, 0, 100, 100)
        parent_img = Image.new("RGB", (100, 100))
        ctx = PaintContext(parent_img, ImageDraw.Draw(parent_img), clip)

        c._do_draw(ctx, frame)

        # Child frame doesn't intersect clip → not drawn
        assert len(drawn_frames) == 0


# ---------------------------------------------------------------------------
# ContainerWidget._propagate_dirty scroll offset
# ---------------------------------------------------------------------------

class TestPropagateDirtyScrollOffset:
    """_propagate_dirty must account for self.offset (scroll) when translating
    a local dirty region into parent coordinates."""

    def test_no_scroll_translates_by_box_position(self):
        """Without scrolling, dirty clip should be offset by the container's
        position in the parent."""
        received = []

        class CapturingParent(Widget):
            def _propagate_dirty(self, clip):
                received.append(clip)

        parent = CapturingParent(box=Box(0, 0, 200, 200))
        c = _container(w=100, h=100)
        c.box = Box(20, 30, 120, 130)   # container positioned at (20,30)
        c.parent = parent

        local_clip = Box(10, 10, 50, 50)
        c._propagate_dirty(local_clip)

        assert len(received) == 1
        result = received[0]
        # Expected: local_clip shifted by container position = (30,40,70,80)
        assert result == Box(30, 40, 70, 80)

    def test_scroll_offset_shifts_propagated_clip(self):
        """With a scroll offset of (dx, dy), the propagated clip should be
        shifted by -offset before being translated to parent coords."""
        received = []

        class CapturingParent(Widget):
            def _propagate_dirty(self, clip):
                received.append(clip)

        parent = CapturingParent(box=Box(0, 0, 200, 200))
        c = _container(w=100, h=100)
        c.box = Box(20, 30, 120, 130)
        c.parent = parent
        c.offset = (5, 10)   # scrolled: content shifted by (5,10)

        local_clip = Box(10, 10, 50, 50)
        c._propagate_dirty(local_clip)

        assert len(received) == 1
        result = received[0]
        # deoffset(5,10) → (5,0,45,40), then offset by (20,30) → (25,30,65,70)
        assert result == Box(25, 30, 65, 70)
