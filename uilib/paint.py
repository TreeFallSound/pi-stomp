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

from dataclasses import dataclass
from typing import Generator, Tuple, Protocol
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
    """

    image: Image.Image
    draw: ImageDraw.ImageDraw
    clip: Box
    pool: BufferManager = _NAIVE_POOL

    @contextmanager
    def painting(self, frame: Box) -> Generator[Tuple["PaintContext", Box], None, None]:
        """Yield (paint_ctx, paint_frame) suitable for painting `frame`.

        Fast path  (clip ⊇ frame): yields (self, frame). __exit__ is a no-op.
        Slow path  (clip ∩ frame is sub-region): yields a temp-backed ctx
                   sized exactly to the intersection, with origin re-anchored.
                   __exit__ composites temp into self.image.
        """
        if self.clip.contains(frame):
            yield self, frame
            return

        visible = self.clip.intersection(frame)
        if visible.is_empty():
            # This should have been caught by the caller, but handle it gracefully
            yield self, frame
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
            pctx = PaintContext(temp, temp_draw, pclip, self.pool)

            yield pctx, pframe

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
