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

from functools import lru_cache
from typing import Generator, Protocol, runtime_checkable

from PIL import Image, ImageDraw, ImageFont


@runtime_checkable
class Glyph(Protocol):
    def width(self, font_height: int) -> int: ...
    def draw(self, draw: ImageDraw.ImageDraw, x: int, y: int, font_height: int, color) -> None: ...


class PillGlyph:
    """Rounded-rectangle badge with a short label rendered in a small font."""

    def __init__(self, label: str, font_size: int = 9) -> None:
        self._label = label
        self._font = ImageFont.truetype("DejaVuSans.ttf", font_size)
        bb = self._font.getbbox(label)
        self._text_w = int(bb[2] - bb[0])
        self._text_h = int(bb[3] - bb[1])
        self._text_bb = bb

    def width(self, font_height: int) -> int:
        return self._text_w + 8 + 2  # +2 for 1px breathing on each side

    def draw(self, draw: ImageDraw.ImageDraw, x: int, y: int, font_height: int, color) -> None:
        draw._image.paste(self._render(font_height, int(color)), (x, y))  # type: ignore[attr-defined]

    @lru_cache(maxsize=16)
    def _render(self, font_height: int, color: int) -> Image.Image:
        cell_w = self.width(font_height)
        img = Image.new("L", (cell_w, font_height), 0)
        d = ImageDraw.Draw(img)
        bw = cell_w - 2
        bx = 1
        bh = self._text_h + 4
        by = max(0, (font_height - bh) // 2)
        d.rounded_rectangle([bx, by, bx + bw - 1, by + bh - 1], radius=2, fill=color, outline=None)
        tx = bx + (bw - self._text_w) // 2 - int(self._text_bb[0])
        ty = by + 2 - int(self._text_bb[1])
        d.text((tx, ty), self._label, fill=0, font=self._font)
        return img


class SignalBarsGlyph:
    """Cellphone-style signal strength: slices of a right triangle. Bar 0 is
    a triangle (left edge zero-height); bars 1..n are trapezoids whose tops
    follow a single continuous hypotenuse spanning the full glyph width
    (gaps included). Bars [0:level] are filled; the rest are outlined.
    Rendered via 4x supersampling for anti-aliased edges."""

    SCALE: int = 4

    def __init__(self, level: int, bar_count: int = 4, bar_w: int = 5, gap: int = 2) -> None:
        self._level = max(0, min(bar_count, level))
        self._bar_count = bar_count
        self._bar_w = bar_w
        self._gap = gap

    def width(self, font_height: int) -> int:
        return self._bar_count * self._bar_w + (self._bar_count - 1) * self._gap + 2

    def draw(self, draw: ImageDraw.ImageDraw, x: int, y: int, font_height: int, color) -> None:
        draw._image.paste(self._render(font_height, int(color)), (x, y))  # type: ignore[attr-defined]

    @lru_cache(maxsize=32)
    def _render(self, font_height: int, color: int) -> Image.Image:
        s = self.SCALE
        cell_w = self.width(font_height)
        cell_h = font_height
        big = Image.new("L", (cell_w * s, cell_h * s), 0)
        bd = ImageDraw.Draw(big)

        max_h = max(4, font_height - 4) * s
        baseline = (font_height - 2) * s
        bw = self._bar_w * s
        gap = self._gap * s
        span = (self._bar_count - 1) * (bw + gap) + bw - 1  # leftmost to rightmost pixel

        for i in range(self._bar_count):
            bx_left = s + i * (bw + gap)
            bx_right = bx_left + bw - 1
            h_left = int(round(max_h * (bx_left - s) / span))
            h_right = int(round(max_h * (bx_right - s) / span))
            poly = [
                (bx_left, baseline),
                (bx_right, baseline),
                (bx_right, baseline - h_right),
                (bx_left, baseline - h_left),
            ]
            if i < self._level:
                bd.polygon(poly, fill=color)
            else:
                # Half-intensity in the L-mask → renders dim against the fgnd.
                bd.polygon(poly, outline=color // 2, width=s)

        return big.resize((cell_w, cell_h), Image.Resampling.LANCZOS)


class FontWithGlyphs:
    """Font wrapper that renders custom glyphs for specified sentinel characters.

    All other rendering delegates transparently to the wrapped base font, so
    regular text draws exactly as it would with the base font alone.

    Usage::

        font = FontWithGlyphs(base_font, {MY_CHAR: PillGlyph('P')})
        draw_selection_menu(items, font=font)
    """

    def __init__(self, base: ImageFont.FreeTypeFont, glyphs: dict[str, Glyph]) -> None:
        self._base = base
        self._glyphs = glyphs
        self._ascent, self._descent = base.getmetrics()
        self._font_height = self._ascent + self._descent

    # --- PIL font interface ---

    def getmetrics(self) -> tuple[int, int]:
        return self._base.getmetrics()

    def getbbox(self, text: str, *args, **kwargs) -> tuple[int, int, int, int]:
        if not any(c in text for c in self._glyphs):
            bb = self._base.getbbox(text, *args, **kwargs)
            return (int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3]))

        total_w = 0
        min_top = 0
        max_bottom = 0
        for segment, glyph in self._iter_segments(text):
            if glyph is not None:
                total_w += glyph.width(self._font_height)
                max_bottom = max(max_bottom, self._font_height)
            elif segment:
                bb = self._base.getbbox(segment, *args, **kwargs)
                total_w += int(bb[2]) - int(bb[0])
                min_top = min(min_top, int(bb[1]))
                max_bottom = max(max_bottom, int(bb[3]))
        return (0, min_top, total_w, max_bottom)

    def getmask2(self, text: str, mode: str = "", **kwargs) -> tuple:
        if not any(c in text for c in self._glyphs):
            return self._base.getmask2(text, mode, **kwargs)

        img = Image.new("L", (max(self._measure_width(text), 1), self._font_height), 0)
        draw = ImageDraw.Draw(img)
        x = 0
        for segment, glyph in self._iter_segments(text):
            if glyph is not None:
                glyph.draw(draw, x, 0, self._font_height, 255)
                x += glyph.width(self._font_height)
            elif segment:
                # draw.text applies the font's internal offset automatically,
                # so vertical positioning matches normal single-string rendering.
                draw.text((x, 0), segment, fill=255, font=self._base)
                bb = self._base.getbbox(segment)
                x += int(bb[2]) - int(bb[0])
        return img.im, (0, 0)

    def __getattr__(self, name: str):
        return getattr(self._base, name)

    # --- helpers ---

    def _iter_segments(self, text: str) -> Generator[tuple[str, "Glyph | None"], None, None]:
        """Yield (segment_str, glyph_or_None) pairs for each run in text."""
        buf = ""
        for ch in text:
            glyph = self._glyphs.get(ch)
            if glyph is not None:
                if buf:
                    yield buf, None
                    buf = ""
                yield ch, glyph
            else:
                buf += ch
        if buf:
            yield buf, None

    def _measure_width(self, text: str) -> int:
        total = 0
        for segment, glyph in self._iter_segments(text):
            if glyph is not None:
                total += glyph.width(self._font_height)
            elif segment:
                bb = self._base.getbbox(segment)
                total += int(bb[2]) - int(bb[0])
        return total
