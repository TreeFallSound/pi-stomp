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
from typing import Generator, Optional, Tuple
from contextlib import contextmanager
from PIL import Image, ImageDraw

from uilib.box import Box


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
        # We always return an image of the max_size to avoid repeated allocations
        # if sizes vary slightly. Clear it to transparent.
        if self._free:
            img = self._free.pop()
        else:
            img = Image.new("RGBA", self.max_size, (0, 0, 0, 0))
        
        # Clear the region we might use. Actually, it's safer to clear the whole thing
        # or at least the requested size. PIL's paste((0,0,0,0), ...) or similar.
        # Simplest is just to create a new one if it's the first time, and clear it.
        # For reuse, clearing the requested size is enough.
        # img.paste((0, 0, 0, 0), (0, 0, size[0], size[1]))
        
        # Actually, clearing the whole image is fast and safer.
        img.paste((0, 0, 0, 0), (0, 0, img.size[0], img.size[1]))
        return img

    def release(self, buf: Image.Image) -> None:
        self._free.append(buf)


@dataclass(frozen=True)
class PaintContext:
    """Immutable paint state passed down the widget tree.

    image : target surface being drawn into
    draw  : cached ImageDraw for image
    clip  : dirty rect in image-coordinate space
    pool  : optional buffer pool for slow-path clipping
    """
    image: Image.Image
    draw: ImageDraw.ImageDraw
    clip: Box
    pool: Optional[BufferPool] = None

    @contextmanager
    def painting(self, frame: Box) -> Generator[Tuple['PaintContext', Box], None, None]:
        """Yield (paint_ctx, paint_frame) suitable for painting `frame`.

        Fast path  (clip ⊇ frame): yields (self, frame). __exit__ is a no-op.
        Slow path  (clip ⊊ frame): yields a temp-backed ctx with origin
                                    re-anchored to (0,0). __exit__ composites
                                    visible ∩ frame into self.image.
        """
        if self.clip.contains(frame):
            yield self, frame
            return

        # Slow path
        if self.pool is None:
            # Fallback to a one-off buffer if no pool provided (e.g. in tests)
            temp = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        else:
            temp = self.pool.acquire(frame.size)

        try:
            temp_draw = ImageDraw.Draw(temp)
            # Re-anchored frame for the temp buffer
            pframe = Box(0, 0, frame.width, frame.height)
            # Clip is the intersection of our clip and the frame, but re-anchored to temp
            pclip = self.clip.intersection(frame).deoffset(frame.topleft)
            pctx = PaintContext(temp, temp_draw, pclip, self.pool)
            
            yield pctx, pframe

            # Composite result back to self.image
            # We only composite the intersection of clip and frame
            visible = self.clip.intersection(frame)
            if not visible.is_empty():
                src_rect = visible.deoffset(frame.topleft).rect
                crop = temp.crop(src_rect)
                dest_topleft = visible.topleft
                
                if self.image.mode == 'RGBA':
                    self.image.alpha_composite(crop, dest_topleft)
                else:
                    # RGB target uses paste with mask
                    self.image.paste(crop, dest_topleft, crop)
        finally:
            if self.pool is not None:
                self.pool.release(temp)
