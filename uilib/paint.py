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
from typing import Generator, Optional, Sequence, Tuple, Union
from contextlib import contextmanager

from uilib.pygame_init import freetype as _get_freetype

# Initializes pygame + freetype (sets the headless SDL driver) and returns the
# module — must run before `import pygame` so the driver is set first.
_freetype = _get_freetype()

import pygame
import pygame.gfxdraw as gfxdraw

from uilib.box import Box
from uilib.radius import Radius


# Color spec accepted by uilib's PaintContext primitives.
ColorLike = Union[pygame.Color, str, int, Tuple[int, int, int], Tuple[int, int, int, int], Sequence[int]]
Point = Tuple[int, int]
PointSeq = Sequence[Point]
FlatCoords = Sequence[int]


def _color(c: ColorLike) -> pygame.Color:
    """Coerce a non-None color spec to a pygame.Color."""
    if isinstance(c, pygame.Color):
        return c
    if isinstance(c, str):
        return pygame.Color(c)
    return pygame.Color(*c) if not isinstance(c, int) else pygame.Color(c)


def _ipt(p: Sequence[int]) -> Point:
    return (int(p[0]), int(p[1]))


def _pg_rect(box: Box) -> pygame.Rect:
    return pygame.Rect(int(box.x0), int(box.y0), max(0, int(box.width)), max(0, int(box.height)))


@dataclass(frozen=True)
class PaintContext:
    """Immutable paint state passed down the widget tree.

    surface : pygame.Surface being drawn into
    clip    : dirty rect in surface-coordinate space
    frame   : the current widget's rect in surface-coordinate space; widget-relative
              drawing methods translate (0,0) → frame.topleft. None on root
              contexts before painting() has been entered.
    """

    surface: pygame.Surface
    clip: Box
    frame: Optional[Box] = None

    # --- Widget-relative geometry helpers ---

    def _f(self) -> Box:
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
        """Widget-relative dirty rect: bounds ∩ (clip in widget coords)."""
        f = self._f()
        return self.bounds.intersection(self.clip.deoffset(f.topleft))

    def _abs_xy(self, xy: Sequence[int]) -> Point:
        ox, oy = self._f().topleft
        return (int(xy[0]) + ox, int(xy[1]) + oy)

    def _abs_box(self, box: Box) -> Box:
        return box.offset(self._f().topleft)

    def _abs_points(self, xy: Union[PointSeq, FlatCoords]) -> Sequence[Point]:
        ox, oy = self._f().topleft
        if len(xy) == 0:
            return []
        first = xy[0]
        if isinstance(first, (tuple, list)):
            return [(int(p[0]) + ox, int(p[1]) + oy) for p in xy]  # type: ignore[index]
        out: list[Point] = []
        for i in range(0, len(xy), 2):
            out.append((int(xy[i]) + ox, int(xy[i + 1]) + oy))  # type: ignore[arg-type]
        return out

    # --- Widget-relative drawing primitives ---

    def fill(self, color: ColorLike) -> None:
        self.surface.fill(_color(color), _pg_rect(self._abs_box(self.bounds)))

    def draw_rectangle(
        self,
        box: Box,
        fill: Optional[ColorLike] = None,
        outline: Optional[ColorLike] = None,
        width: int = 0,
        radius: int | Radius | None = None,
    ) -> None:
        rect = _pg_rect(self._abs_box(box))
        if rect.width <= 0 or rect.height <= 0:
            return
        kwargs = Radius._coerce(radius).as_pygame_kwargs()
        if fill is not None:
            pygame.draw.rect(self.surface, _color(fill), rect, 0, **kwargs)
        if outline is not None and int(width) > 0:
            pygame.draw.rect(self.surface, _color(outline), rect, int(width), **kwargs)

    def draw_ellipse(
        self, box: Box, fill: Optional[ColorLike] = None, outline: Optional[ColorLike] = None, width: int = 0
    ) -> None:
        """Draw a non-AA ellipse matching PIL's ImageDraw.ellipse aesthetic.

        gfxdraw.filled_ellipse for the fill (closest coverage to PIL),
        pygame.draw.ellipse with width for the outline (PIL-equivalent jaggy
        stroke; handles thick widths natively). AA versions blend edges to
        semi-transparent gray which clashes with the design language."""
        rect = _pg_rect(self._abs_box(box))
        # XXX: adding 1 to width/height gave us parity with Pillow...
        rect.width += 1
        rect.height += 1
        if rect.width <= 0 or rect.height <= 0:
            return
        if fill is not None:
            # gfxdraw.filled_ellipse covers [cx-rx, cx+rx] inclusive (2*rx+1
            # pixels). To fill the full Box, use rx = (width-1)//2 and place
            # the center on the upper-left of the two center pixels for even
            # sizes — matches PIL's coverage exactly.
            cx = rect.x + (rect.width - 1) // 2
            cy = rect.y + (rect.height - 1) // 2
            rx = max(0, (rect.width - 1) // 2)
            ry = max(0, (rect.height - 1) // 2)
            gfxdraw.filled_ellipse(self.surface, cx, cy, rx, ry, _color(fill))
        if outline is not None and int(width) > 0:
            pygame.draw.ellipse(self.surface, _color(outline), rect, int(width))

    def draw_line(self, xy: Union[PointSeq, FlatCoords], fill: Optional[ColorLike] = None, width: int = 0) -> None:
        """Draw a polyline.

        PIL stamps a `width`×`width` box at each step along the bresenham path,
        so diagonals end up ~1px thicker than axis-aligned strokes of the same
        nominal width. pygame strokes exactly `width` perpendicular to the
        segment. To match PIL's visual weight on icon knob pointers / pedal
        graphics, bump width by 1 for non-axis-aligned segments when width>=2.
        """
        if fill is None:
            return
        color = _color(fill)
        w = max(1, int(width))
        pts = self._abs_points(xy)
        if len(pts) < 2:
            return
        ipts = [_ipt(p) for p in pts]
        for i in range(len(ipts) - 1):
            p0, p1 = ipts[i], ipts[i + 1]
            seg_w = w if (p0[0] == p1[0] or p0[1] == p1[1] or w < 2) else w + 1
            pygame.draw.line(self.surface, color, p0, p1, seg_w)

    def draw_text(
        self,
        pos: Sequence[int],
        text: str,
        fill: Optional[ColorLike] = None,
        font: Optional[_freetype.Font] = None,
        anchor: Optional[str] = None,
    ) -> None:
        """Draw text using a pygame._freetype Font.

        Default anchor matches PIL's `la` (left, ascender): `pos` is the
        top-left of the line box (ascender line), not of the visible glyph
        bbox. This keeps text vertical alignment consistent regardless of
        which characters appear (with/without ascenders or descenders).
        Also supports anchor='mm' (middle/middle of the glyph bbox).
        """
        if not text or font is None or fill is None:
            return
        color = _color(fill)
        x, y = self._abs_xy(pos)
        asc = int(font.get_sized_ascender())
        if anchor == "mm":
            # PIL anchor='mm' centers on (PIL.getbbox(text).w / 2, (asc+desc)/2).
            # uilib.misc.get_text_size matches PIL getbbox semantics. Use int()
            # (floor for positive operands) — not round() — because PIL's BASIC
            # layout effectively floors the fractional pen position; Python's
            # banker's rounding on .5 boundaries (e.g. 51.5 → 52) would push
            # the glyph one pixel right of PIL.
            from uilib.misc import get_text_size

            desc = abs(int(font.get_sized_descender()))
            tw, _ = get_text_size(text, font)
            base_dst = (int(x - tw / 2), int(y - (asc + desc) / 2))
        else:
            base_dst = (int(x), int(y))
        # pygame._freetype.Font.render_to bypasses surface.set_clip (it clamps
        # only to the destination surface's bounds). To enforce the active
        # clip without a temp+blit, render into a subsurface of the current
        # clip rect — the rasterizer then clamps to that, giving us SDL-style
        # clipping for free. `painting()` guarantees a non-empty clip.
        clip = self.surface.get_clip()
        if clip.width <= 0 or clip.height <= 0:
            return
        sub = self.surface.subsurface(clip)
        pen = (base_dst[0] - clip.x, base_dst[1] + asc - clip.y)
        prev_origin = font.origin
        font.origin = True
        try:
            font.render_to(sub, pen, text, fgcolor=color)
        finally:
            font.origin = prev_origin

    def draw_arc_aa(self, cx: int, cy: int, r: int, clip: Box, color: ColorLike) -> None:
        """AA circle arc clipped to a quadrant box (widget-relative).

        Renders on a fresh SRCALPHA surface so alpha composites correctly
        regardless of the destination format, then blits the clip region.
        """
        size = 2 * r + 1
        tmp = pygame.Surface((size, size), pygame.SRCALPHA)
        tmp.fill((0, 0, 0, 0))
        gfxdraw.aacircle(tmp, r, r, r, _color(color))
        abs_cx, abs_cy = self._abs_xy((cx, cy))
        abs_clip = _pg_rect(self._abs_box(clip))
        src = pygame.Rect(
            abs_clip.x - (abs_cx - r),
            abs_clip.y - (abs_cy - r),
            abs_clip.width,
            abs_clip.height,
        ).clip(pygame.Rect(0, 0, size, size))
        if src.width > 0 and src.height > 0:
            self.surface.blit(tmp, (abs_clip.x, abs_clip.y), area=src)

    def paste(self, src: pygame.Surface, pos: Sequence[int], mask: Optional[pygame.Surface] = None) -> None:
        """Blit a surface onto self.surface at widget-relative coords."""
        self.surface.blit(src, _ipt(self._abs_xy(pos)))

    @contextmanager
    def painting(self, frame: Box) -> Generator["PaintContext", None, None]:
        """Yield a PaintContext scoped to `frame`.

        Sets an SDL clip rectangle = clip ∩ frame so primitives that draw past
        the widget's frame are silently dropped. Pops the previous clip on exit.
        """
        visible = self.clip.intersection(frame)
        if visible.is_empty():
            yield replace(self, frame=frame, clip=visible)
            return
        old_clip = self.surface.get_clip()
        self.surface.set_clip(_pg_rect(visible))
        try:
            yield replace(self, frame=frame, clip=visible)
        finally:
            self.surface.set_clip(old_clip)
