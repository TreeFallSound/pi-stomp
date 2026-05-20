"""
Unit tests for paint-context drawing logic:
  - Box.contains
  - Widget._draw_erase (safe-interior vs full-frame erase)
  - ContainerWidget.propagate_dirty scroll-offset translation
"""

import pytest
from PIL import Image, ImageDraw

from uilib.box import Box
from uilib.paint import PaintContext, BufferPool
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
        edge = Box(0, 0, 100, 50)  # shares top/left/right edge
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
        empty = Box(50, 50, 50, 50)  # zero-area
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
        ctx = PaintContext(img, draw, clip, frame=frame)

        w = Widget(box=frame)
        w.outline_radius = outline_radius
        w.bkgnd_color = (0, 0, 0)

        w._draw_erase(ctx)
        return img

    def test_no_radius_erases_only_clip(self):
        frame = Box(0, 0, 100, 100)
        clip = Box(10, 10, 50, 50)
        img = self._erase_and_read(clip, frame, outline_radius=None)
        # Clipped region is black
        assert img.getpixel((20, 20)) == (0, 0, 0)
        # Outside clip stays white
        assert img.getpixel((80, 80)) == (255, 255, 255)

    def test_radius_safe_interior_erases_only_clip(self):
        """Dirty region inside the safe interior → plain rect erase."""
        frame = Box(0, 0, 100, 100)
        r = 10
        # clip well inside the safe zone (r..100-r on each axis)
        clip = Box(20, 20, 80, 80)
        img = self._erase_and_read(clip, frame, outline_radius=r)
        assert img.getpixel((50, 50)) == (0, 0, 0)  # inside clip → erased
        assert img.getpixel((5, 5)) == (255, 255, 255)  # corner → untouched

    def test_radius_partial_clip_erases_only_intersection(self):
        """Partial clip on a rounded widget → plain rect erase of the intersection.
        Full-frame expansion for rounded shapes is ContainerWidget.do_draw's job,
        not _draw_erase's.  A leaf widget with outline_radius still gets a rect
        erase when the clip is smaller than the frame."""
        frame = Box(0, 0, 100, 100)
        r = 10
        clip = Box(0, 0, 20, 20)
        img = self._erase_and_read(clip, frame, outline_radius=r)
        # Only the clipped region is erased
        assert img.getpixel((10, 10)) == (0, 0, 0)
        # Centre untouched — no full-frame expansion at this level
        assert img.getpixel((50, 50)) == (255, 255, 255)

    def test_radius_full_frame_uses_rounded_rectangle(self):
        """When clip == frame, always use rounded_rectangle (corners preserved)."""
        frame = Box(0, 0, 100, 100)
        r = 10
        img = self._erase_and_read(frame, frame, outline_radius=r)
        # Centre erased
        assert img.getpixel((50, 50)) == (0, 0, 0)
        # Absolute corner pixels NOT erased (rounded rect leaves them)
        assert img.getpixel((0, 0)) == (255, 255, 255)


# ---------------------------------------------------------------------------
# BufferPool
# ---------------------------------------------------------------------------


class TestBufferPool:
    def test_best_fit_allocation(self):
        pool = BufferPool((320, 240))

        # 1. First allocation
        img1 = pool.acquire((100, 100))
        assert img1.size == (100, 100)
        pool.release(img1)

        # 2. Exact match reuse
        img2 = pool.acquire((100, 100))
        assert img2 is img1
        pool.release(img2)

        # 3. New allocation for larger request
        img3 = pool.acquire((150, 150))
        assert img3.size == (150, 150)
        assert img3 is not img1
        pool.release(img3)

        # 4. Best fit reuse: img1(100x100) and img3(150x150) are free.
        # Request for 120x120 should take img3.
        img4 = pool.acquire((120, 120))
        assert img4 is img3
        pool.release(img4)

        # Request for 80x80 should take img1.
        img5 = pool.acquire((80, 80))
        assert img5 is img1
        pool.release(img5)

    def test_max_size_cap(self):
        pool = BufferPool((100, 100))
        img = pool.acquire((200, 200))
        assert img.size == (100, 100)

    def test_pool_lifecycle_and_nesting(self):
        """Verify that pool size is bounded by nesting depth, not operation count."""
        pool = BufferPool((320, 240))
        img = Image.new("RGBA", (320, 240))
        draw = ImageDraw.Draw(img)

        # Force slow path with a small clip
        ctx = PaintContext(img, draw, Box(0, 0, 5, 5), pool)

        # 1. Serial draws (should reuse same buffer)
        for _ in range(100):
            with ctx.painting(Box(0, 0, 100, 100)):
                pass
        assert len(pool._free) == 1

        # 2. Nested draws (should grow to depth)
        with ctx.painting(Box(0, 0, 100, 100)) as ctx2:
            # Inner clip must also be 'slow path' relative to ctx2.clip
            # ctx2.clip is (0,0,5,5) re-anchored.
            with ctx2.painting(Box(0, 0, 100, 100)):
                assert len(pool._free) == 0  # 2 are currently active
            assert len(pool._free) == 1  # Inner released
        assert len(pool._free) == 2  # Both released


class TestPropagateDirtyScrollOffset:
    """propagate_dirty must account for self.offset (scroll) when translating
    a local dirty region into parent coordinates."""

    def test_no_scroll_translates_by_box_position(self):
        """Without scrolling, dirty clip should be offset by the container's
        position in the parent."""
        received = []

        class CapturingParent(Widget):
            def propagate_dirty(self, clip):
                received.append(clip)

        parent = CapturingParent(box=Box(0, 0, 200, 200))
        c = _container(w=100, h=100)
        c.box = Box(20, 30, 120, 130)  # container positioned at (20,30)
        c.parent = parent

        local_clip = Box(10, 10, 50, 50)
        c.propagate_dirty(local_clip)

        assert len(received) == 1
        result = received[0]
        # Expected: local_clip shifted by container position = (30,40,70,80)
        assert result == Box(30, 40, 70, 80)

    def test_scroll_offset_shifts_propagated_clip(self):
        """With a scroll offset of (dx, dy), the propagated clip should be
        shifted by -offset before being translated to parent coords."""
        received = []

        class CapturingParent(Widget):
            def propagate_dirty(self, clip):
                received.append(clip)

        parent = CapturingParent(box=Box(0, 0, 200, 200))
        c = _container(w=100, h=100)
        c.box = Box(20, 30, 120, 130)
        c.parent = parent
        c.offset = (5, 10)  # scrolled: content shifted by (5,10)

        local_clip = Box(10, 10, 50, 50)
        c.propagate_dirty(local_clip)

        assert len(received) == 1
        result = received[0]
        # deoffset(5,10) → (5,0,45,40), then offset by (20,30) → (25,30,65,70)
        assert result == Box(25, 30, 65, 70)


# ---------------------------------------------------------------------------
# Relative-coordinate API contract
# ---------------------------------------------------------------------------


class _RelDrawWidget(Widget):
    """Test widget that draws via the relative-coord PaintContext API.

    Fills its own background, draws a 1-pixel marker at relative (0,0), and a
    single-pixel rectangle at the opposite corner. Any frame translation bug
    surfaces as a marker landing at the wrong absolute coordinate.
    """

    def _draw(self, ctx):
        ctx.fill((255, 255, 255))
        ctx.draw_rectangle(Box(0, 0, 1, 1), fill=(255, 0, 0))
        ctx.draw_rectangle(Box(ctx.width - 1, ctx.height - 1, ctx.width, ctx.height),
                           fill=(0, 255, 0))


class TestRelativeCoords:
    """The wrappers must translate (0,0) → frame.topleft for any frame placement."""

    @pytest.mark.parametrize("frame", [
        Box(0, 0, 20, 20),       # at origin
        Box(50, 30, 70, 50),     # offset into image
        Box(99, 99, 119, 119),   # straddling beyond image (rest clipped naturally)
    ])
    def test_origin_marker_lands_at_frame_topleft(self, frame):
        img = Image.new("RGB", (200, 200), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        ctx = PaintContext(img, draw, Box(0, 0, 200, 200))

        w = _RelDrawWidget(box=frame)
        w.bkgnd_color = (0, 0, 0)
        w.fgnd_color = (255, 255, 255)
        w.do_draw(ctx, frame)

        # (0,0) marker lands at frame.topleft.
        assert img.getpixel(frame.topleft) == (255, 0, 0)
        # (width-1, height-1) marker lands at frame's botright minus 1.
        far = (frame.x1 - 1, frame.y1 - 1)
        if 0 <= far[0] < 200 and 0 <= far[1] < 200:
            assert img.getpixel(far) == (0, 255, 0)
        # Pixel just outside top-left is still untouched.
        if frame.x0 > 0:
            assert img.getpixel((frame.x0 - 1, frame.y0)) == (0, 0, 0)


# ---------------------------------------------------------------------------
# Slow-path scissor containment
# ---------------------------------------------------------------------------


class _SloppyWidget(Widget):
    """Intentionally draws well outside its own frame to test the slow-path
    scissor. A correctly-clipping PaintContext must discard any pixels that
    fall outside clip ∩ frame."""

    def _draw(self, ctx):
        # Try to bleed 10px past every edge.
        ctx.draw_rectangle(
            Box(-10, -10, ctx.width + 10, ctx.height + 10),
            fill=(255, 0, 0),
        )


class TestSloppyDrawContainment:
    """A widget that paints outside its frame must NOT leak onto the parent
    surface beyond clip ∩ frame when the slow path is engaged."""

    def test_slow_path_scissors_oversized_draw(self):
        from uilib.paint import BufferPool

        img = Image.new("RGBA", (200, 200), (0, 0, 0, 255))
        draw = ImageDraw.Draw(img)

        # Force slow path: clip is a strict sub-rect of frame.
        frame = Box(50, 50, 150, 150)
        clip = Box(60, 60, 140, 140)
        pool = BufferPool((200, 200))
        ctx = PaintContext(img, draw, clip, pool)

        w = _SloppyWidget(box=frame)
        w.bkgnd_color = (0, 0, 0, 0)  # transparent erase so we see leaks clearly
        w.fgnd_color = (255, 255, 255)
        w.do_draw(ctx, frame)

        # Inside clip: should be red (widget drew there).
        assert img.getpixel((100, 100))[:3] == (255, 0, 0)

        # Outside clip but inside frame: widget *tried* to paint here via the
        # oversized rect, but the slow-path scissor must have dropped it.
        # frame extends [50,150)×[50,150); clip is [60,140)×[60,140).
        # Pixel (55, 100) is inside frame, outside clip.
        assert img.getpixel((55, 100))[:3] == (0, 0, 0)
        assert img.getpixel((145, 100))[:3] == (0, 0, 0)
        assert img.getpixel((100, 55))[:3] == (0, 0, 0)

        # Well outside frame: definitely untouched.
        assert img.getpixel((10, 10))[:3] == (0, 0, 0)
        assert img.getpixel((190, 190))[:3] == (0, 0, 0)
