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

from uilib._pygame_init import init as _pg_init

_pg_init()

import pygame
import pygame._freetype as _freetype
import pygame.gfxdraw as gfxdraw

from uilib.box import Box


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
        radius: Optional[int] = None,
    ) -> None:
        rect = _pg_rect(self._abs_box(box))
        if rect.width <= 0 or rect.height <= 0:
            return
        border_radius = int(radius) if radius is not None else 0
        if fill is not None:
            pygame.draw.rect(self.surface, _color(fill), rect, 0, border_radius=border_radius)
        if outline is not None and int(width) > 0:
            pygame.draw.rect(self.surface, _color(outline), rect, int(width), border_radius=border_radius)

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
        # IMPORTANT: pygame._freetype.Font.render_to bypasses surface.set_clip
        # — confirmed in pygame-ce src_c/freetype/ft_render*.c, where the
        # rasterizer locks the destination surface and clamps only against
        # full surface bounds, never consulting clip_rect. Surface.blit DOES
        # honor the clip.
        #
        # We render into a line-height-sized temp surface with the baseline
        # at the ascender position inside it (origin=True), so the glyph
        # vertically lives at the same offset from the temp top that PIL's
        # 'la' anchor produced (bbox[1] = ascender - glyph_top). Blitting the
        # temp at (x, y) then puts pixels at the same absolute coords PIL
        # would have, but the blit IS clip-respecting.
        asc = int(font.get_sized_ascender())
        desc = abs(int(font.get_sized_descender()))
        rect = font.get_rect(text)
        # font.get_rect(text).x is the left-side bearing — render at -rect.x so the
        # leftmost visible glyph pixel lands at temp x=0 (PIL `la` semantics).
        # Per-glyph descent below the nominal font descender (e.g. 'g','p','y')
        # must extend the temp height; matches misc.get_text_size().
        glyph_desc = 0
        for m in font.get_metrics(text):
            if m is None:
                continue
            min_y = m[2]
            if min_y >= 0x80000000:
                min_y -= 0x100000000
            if min_y < 0 and -min_y > glyph_desc:
                glyph_desc = -min_y
        # PIL `la` puts the pen at `pos`; ink lands at pos.x + lsb. When the
        # first glyph has negative LSB (e.g. 'j' rect.x=-1), the ink dips left
        # of the pen, and our temp surface must include that overhang or the
        # leftmost ink column will be clipped. Pad `pad_x` columns on the
        # left, render the pen at temp_x=pad_x, and blit with dst.x shifted
        # left by pad_x so the final ink lands at the same dst column as the
        # PIL output (= base_dst_x + rect.x).
        pad_x = max(0, -rect.x)
        temp_w = max(1, rect.x + rect.width + pad_x)
        temp_h = max(1, asc + desc + glyph_desc)
        temp = pygame.Surface((temp_w, temp_h), pygame.SRCALPHA)
        prev_origin = font.origin
        font.origin = True
        try:
            font.render_to(temp, (pad_x, asc), text, fgcolor=color)
        finally:
            font.origin = prev_origin
        if anchor == "mm":
            # PIL anchor='mm' centers on (PIL.getbbox(text).w / 2, (asc+desc)/2).
            # uilib.misc.get_text_size matches PIL getbbox semantics. Use int()
            # (floor for positive operands) — not round() — because PIL's BASIC
            # layout effectively floors the fractional pen position; Python's
            # banker's rounding on .5 boundaries (e.g. 51.5 → 52) would push
            # the glyph one pixel right of PIL.
            from uilib.misc import get_text_size
            tw, _ = get_text_size(text, font)
            base_dst = (int(x - tw / 2), int(y - (asc + desc) / 2))
        else:
            base_dst = (int(x), int(y))
        dst = (base_dst[0] - pad_x, base_dst[1])
        self.surface.blit(temp, dst)

    def paste(self, src: pygame.Surface, pos: Sequence[int], mask: Optional[pygame.Surface] = None) -> None:
        """Blit a surface onto self.surface at widget-relative coords."""
        self.surface.blit(src, _ipt(self._abs_xy(pos)))

    def alpha_composite(
        self, src: pygame.Surface, pos: Sequence[int] = (0, 0), src_box: Optional[Tuple[int, int, int, int]] = None
    ) -> None:
        """SRCALPHA blit. Retained for API parity; equivalent to a normal blit
        when src has per-pixel alpha (pygame handles compositing automatically)."""
        dst = _ipt(self._abs_xy(pos))
        if src_box is None:
            self.surface.blit(src, dst)
        else:
            self.surface.blit(src, dst, area=pygame.Rect(*src_box))

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
