# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

from dataclasses import dataclass, replace
from typing import Generator, Optional, Tuple, Protocol
from contextlib import contextmanager
from PIL import Image, ImageDraw

from uilib.box import Box


class BufferManager(Protocol):
    """Protocol for providing RGBA buffers."""

    def acquire(self, size: Tuple[int, int]) -> Image.Image: ...
    def release(self, buf: Image.Image) -> None: ...


class NaiveBufferPool:
    """Naive implementation that always allocates a new image."""

    def acquire(self, size: Tuple[int, int]) -> Image.Image:
        return Image.new("RGBA", size, (0, 0, 0, 0))

    def release(self, buf: Image.Image) -> None:
        pass


_NAIVE_POOL = NaiveBufferPool()


class BufferPool:
    """Stack of reusable RGBA buffers sized up to (max_w, max_h).

    Used as a stack to support reentrant slow paths (slow-path widget
    contains a slow-path child). Each acquire returns a buffer of at
    least the requested size; the buffer is cleared on acquire and
    returned to the pool on release. No allocation after warm-up."""

    def __init__(self, max_size: Tuple[int, int]):
        self.max_size = max_size
        self._free: list[Image.Image] = []

    def acquire(self, size: Tuple[int, int]) -> Image.Image:
        # 1. Look for the best existing buffer: smallest one that's at least as big as 'size'
        #    on both dimensions.
        best_idx = -1
        best_area = -1

        for i, img in enumerate(self._free):
            if img.size[0] >= size[0] and img.size[1] >= size[1]:
                area = img.size[0] * img.size[1]
                if best_idx == -1 or area < best_area:
                    best_idx = i
                    best_area = area

        if best_idx != -1:
            img = self._free.pop(best_idx)
        else:
            # 2. No suitable buffer found. Allocate exactly what's needed,
            #    capped by max_size.
            alloc_size = (min(size[0], self.max_size[0]), min(size[1], self.max_size[1]))
            img = Image.new("RGBA", alloc_size, (0, 0, 0, 0))

        # Clear the region we will use
        img.paste((0, 0, 0, 0), (0, 0, size[0], size[1]))
        return img

    def release(self, buf: Image.Image) -> None:
        self._free.append(buf)


@dataclass(frozen=True)
class PaintContext:
    """Immutable paint state passed down the widget tree.

    image : target surface being drawn into
    draw  : cached ImageDraw for image
    clip  : dirty rect in image-coordinate space
    pool  : buffer pool for slow-path clipping (defaults to a naive impl)
    frame : the current widget's rect in image-coordinate space; widget-relative
            drawing methods translate (0,0) → frame.topleft. None on root
            contexts before painting() has been entered.
    """

    image: Image.Image
    draw: ImageDraw.ImageDraw
    clip: Box
    pool: BufferManager = _NAIVE_POOL
    frame: Optional[Box] = None

    # --- Widget-relative geometry helpers ---

    def _f(self) -> Box:
        """Return frame, asserting it has been set (drawing requires it)."""
        assert self.frame is not None, "PaintContext drawing requires a frame; enter via painting()"
        return self.frame

    @property
    def width(self) -> int:
        return self._f().width

    @property
    def height(self) -> int:
        return self._f().height

    @property
    def bounds(self) -> Box:
        """The widget's own coordinate space: Box(0, 0, width, height)."""
        f = self._f()
        return Box(0, 0, f.width, f.height)

    @property
    def dirty_bounds(self) -> Box:
        """Widget-relative dirty rect: bounds ∩ (clip in widget coords).

        On the fast path this equals `bounds` whenever the clip fully covers
        the frame. On the slow path the clip is the temp's own bounds and the
        frame is re-anchored, so this still resolves to the widget-visible
        sub-rect."""
        f = self._f()
        return self.bounds.intersection(self.clip.deoffset(f.topleft))

    def _abs_xy(self, xy):
        ox, oy = self._f().topleft
        return (xy[0] + ox, xy[1] + oy)

    def _abs_box(self, box: Box) -> Box:
        return box.offset(self._f().topleft)

    def _abs_points(self, xy):
        """Translate a sequence of points (2-tuples) or a flat coord tuple."""
        ox, oy = self._f().topleft
        if len(xy) == 0:
            return xy
        if isinstance(xy[0], (tuple, list)):
            return [(p[0] + ox, p[1] + oy) for p in xy]
        out = []
        for i in range(0, len(xy), 2):
            out.append(xy[i] + ox)
            out.append(xy[i + 1] + oy)
        return tuple(out)

    # --- Widget-relative drawing primitives ---

    def fill(self, color):
        """Fill the widget's frame with `color`."""
        self.draw.rectangle(self._f().PIL_rect, color, None, 0)

    def draw_rectangle(self, box: Box, fill=None, outline=None, width=0, radius=None):
        ab = self._abs_box(box)
        if radius is None:
            self.draw.rectangle(ab.PIL_rect, fill, outline, width)
        else:
            self.draw.rounded_rectangle(ab.PIL_rect, radius, fill, outline, width)

    def draw_ellipse(self, box: Box, fill=None, outline=None, width=0):
        ab = self._abs_box(box)
        self.draw.ellipse(ab.rect, fill=fill, outline=outline, width=width)

    def draw_line(self, xy, fill=None, width=0):
        self.draw.line(self._abs_points(xy), fill=fill, width=width)

    def draw_text(self, pos, text, fill=None, font=None, anchor=None):
        self.draw.text(self._abs_xy(pos), text, fill=fill, font=font, anchor=anchor)

    def paste(self, src, pos, mask=None):
        self.image.paste(src, self._abs_xy(pos), mask)

    def alpha_composite(self, src, pos=(0, 0), src_box=None):
        if src_box is None:
            self.image.alpha_composite(src, self._abs_xy(pos))
        else:
            self.image.alpha_composite(src, self._abs_xy(pos), src_box)

    @contextmanager
    def painting(self, frame: Box) -> Generator["PaintContext", None, None]:
        """Yield a PaintContext suitable for painting `frame`.

        Fast path  (clip ⊇ frame): yields self with frame set. __exit__ is a no-op.
        Slow path  (clip ∩ frame is sub-region): yields a temp-backed ctx
                   sized exactly to the intersection, with origin re-anchored.
                   __exit__ composites temp into self.image.
        """
        if self.clip.contains(frame):
            yield replace(self, frame=frame)
            return

        visible = self.clip.intersection(frame)
        if visible.is_empty():
            # This should have been caught by the caller, but handle it gracefully
            yield replace(self, frame=frame)
            return

        # Slow path: allocate only what we can actually see
        temp = self.pool.acquire(visible.size)

        try:
            temp_draw = ImageDraw.Draw(temp)
            # Re-anchor: we want the widget to draw at 'frame' relative to 'visible.topleft'
            # So if visible is at (10, 10) and frame is at (0, 0), the widget
            # should draw at (-10, -10) in the temp buffer.
            offset = visible.topleft
            pframe = frame.deoffset(offset)
            pclip = Box(0, 0, visible.width, visible.height)
            pctx = PaintContext(temp, temp_draw, pclip, self.pool, frame=pframe)

            yield pctx

            # Composite result back to self.image. The pool may have handed us
            # a buffer larger than `visible.size`; only the top-left
            # (visible.width, visible.height) region was cleared and painted,
            # so restrict the composite source to that region.
            src_box = (0, 0, visible.width, visible.height)
            if self.image.mode == "RGBA":
                self.image.alpha_composite(temp, visible.topleft, src_box)
            else:
                sub = temp.crop(src_box)
                self.image.paste(sub, visible.topleft, sub)
        finally:
            self.pool.release(temp)
