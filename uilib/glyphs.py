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

"""Custom glyphs for `RichTextWidget` — emoji-style: each one owns its size
and pixels. Constructed with a fixed height; `render()` returns a cached
`pygame.Surface`."""

from functools import lru_cache
from pathlib import Path

import numpy as np
import pygame
from PIL import Image, ImageDraw

from uilib.pygame_init import font as _make_font

_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"
_DEFAULT_COLOR: tuple[int, int, int] = (255, 255, 255)


class PillGlyph:
    """Rounded-rectangle badge with a short label inside.

    Mirrors the PIL original: a 1px-inset rounded rect spanning the glyph
    box, with the label centered horizontally and vertically inside it.
    """

    def __init__(
        self, label: str, height: int, label_size: int = 9, color: tuple[int, int, int] = _DEFAULT_COLOR
    ) -> None:
        self._label = label
        self._height = height
        self._color = color
        self._font = _make_font(_FONTS_DIR / "DejaVuSans.ttf", label_size)
        # Measure once: width is text-driven (text + padding), height is fixed.
        rect = self._font.get_rect(label)
        self._text_w = rect.width
        self._text_h = rect.height
        self._width = self._text_w + 8 + 2  # 4px padding each side + 1px breathing

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def render(self) -> pygame.Surface:
        return self._render_cached(self._color)

    @lru_cache(maxsize=4)
    def _render_cached(self, color: tuple[int, int, int]) -> pygame.Surface:
        surf = pygame.Surface((self._width, self._height), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        # Pill is inset 1px on each side; height is text + 4px of vertical padding.
        bw = self._width - 2
        bx = 1
        bh = self._text_h + 4
        by = max(0, (self._height - bh) // 2)
        pygame.draw.rect(surf, color, pygame.Rect(bx, by, bw, bh), 0, border_radius=2)
        # Punch the label out of the pill by rendering in transparent (color 0).
        # pygame can't render a glyph with alpha=0, so render onto a temp mask
        # and blit-subtract via BLEND_RGBA_SUB? Simpler: render the label dark
        # (assume light-on-dark UI) — matches PIL original which used fill=0
        # on an L-mask getting pasted as a foreground color.
        # Center the label's ink rect (not line box) inside the pill. With
        # origin=False, render_to's pen position is the top-left of the
        # rendered ink — position it directly.
        prev = self._font.origin
        self._font.origin = False
        try:
            rect = self._font.get_rect(self._label)
            tx = bx + (bw - rect.width) // 2
            ty = by + (bh - rect.height) // 2
            self._font.render_to(surf, (tx, ty), self._label, fgcolor=(0, 0, 0))
        finally:
            self._font.origin = prev
        return surf


class SignalBarsGlyph:
    """Cellphone-style signal strength: slices of a right triangle. Bar 0 is
    a triangle (left edge zero-height); bars 1..n are trapezoids whose tops
    follow a single continuous hypotenuse spanning the full glyph width.
    Bars `[0:level]` are filled; the rest are outlined.

    Rendered via 4× supersampling + smoothscale for anti-aliased edges.
    """

    SCALE: int = 4

    def __init__(
        self,
        level: int,
        height: int,
        bar_count: int = 4,
        bar_w: int = 5,
        gap: int = 2,
        color: tuple[int, int, int] = _DEFAULT_COLOR,
    ) -> None:
        self._level = max(0, min(bar_count, level))
        self._height = height
        self._bar_count = bar_count
        self._bar_w = bar_w
        self._gap = gap
        self._color = color
        self._width = bar_count * bar_w + (bar_count - 1) * gap + 2

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def render(self) -> pygame.Surface:
        return self._render_cached(self._color)

    @lru_cache(maxsize=8)
    def _render_cached(self, color: tuple[int, int, int]) -> pygame.Surface:
        # Render in PIL: pygame's smoothscale is bilinear and loses the crisp
        # edges of the supersampled bars. PIL's LANCZOS downscale matches the
        # original pistomp-v3 quality. We render the bars into an L-mask at
        # full intensity (filled = 255, dim = 128) and then tint with the
        # actual color when blitting onto a pygame Surface.
        s = self.SCALE
        cell_w = self._width
        cell_h = self._height
        big = Image.new("L", (cell_w * s, cell_h * s), 0)
        bd = ImageDraw.Draw(big)

        max_h = max(4, cell_h - 4) * s
        baseline = (cell_h - 2) * s
        bw = self._bar_w * s
        gap = self._gap * s
        span = (self._bar_count - 1) * (bw + gap) + bw - 1

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
                bd.polygon(poly, fill=255)
            else:
                bd.polygon(poly, outline=128, width=s)

        mask = big.resize((cell_w, cell_h), Image.Resampling.LANCZOS)
        # Build an RGBA pygame surface: RGB = color, A = mask intensity.
        mask_bytes = mask.tobytes()
        surf = pygame.Surface((cell_w, cell_h), pygame.SRCALPHA)
        pixels = pygame.surfarray.pixels3d(surf)
        alpha = pygame.surfarray.pixels_alpha(surf)
        pixels[:, :, 0] = color[0]
        pixels[:, :, 1] = color[1]
        pixels[:, :, 2] = color[2]
        import numpy as np
        alpha[:, :] = np.frombuffer(mask_bytes, dtype=np.uint8).reshape((cell_h, cell_w)).T
        del pixels, alpha  # release surface locks before returning
        return surf


class EthernetCableGlyph:
    """RJ45 plug silhouette: outlined body with pin ticks and a clip tab below.

    Renders into an RGBA pygame Surface so `IconSeg` can blit it inline like
    any other glyph. Sized to read at typical menu font heights (~22px)."""

    def __init__(self, height: int, body_w: int = 14, color: tuple[int, int, int] = _DEFAULT_COLOR) -> None:
        self._height = height
        self._body_w = body_w
        self._color = color
        self._width = body_w + 2

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def render(self) -> pygame.Surface:
        return self._render_cached(self._color)

    @lru_cache(maxsize=8)
    def _render_cached(self, color: tuple[int, int, int]) -> pygame.Surface:
        # Render via PIL L-mask then tint, same approach as SignalBarsGlyph.
        cell_w = self._width
        cell_h = self._height
        img = Image.new("L", (cell_w, cell_h), 0)
        d = ImageDraw.Draw(img)

        body_h = max(7, cell_h // 2)
        body_w = self._body_w
        body_x = 1
        body_y = max(0, (cell_h - body_h) // 2 - 1)
        d.rectangle([body_x, body_y, body_x + body_w - 1, body_y + body_h - 1],
                    outline=255, width=1)

        # Pin ticks on the right half of the body.
        pin_y0 = body_y + 2
        pin_y1 = body_y + body_h - 3
        for i in range(3):
            px = body_x + body_w - 2 - i * 2
            if px <= body_x + 1:
                break
            d.line([px, pin_y0, px, pin_y1], fill=255, width=1)

        # Clip tab below the body.
        tab_w = max(4, body_w // 3)
        tab_x = body_x + (body_w - tab_w) // 2
        tab_y0 = body_y + body_h
        tab_y1 = min(cell_h - 1, tab_y0 + 1)
        if tab_y1 >= tab_y0:
            d.rectangle([tab_x, tab_y0, tab_x + tab_w - 1, tab_y1], fill=255)

        mask_bytes = img.tobytes()
        surf = pygame.Surface((cell_w, cell_h), pygame.SRCALPHA)
        pixels = pygame.surfarray.pixels3d(surf)
        alpha = pygame.surfarray.pixels_alpha(surf)
        pixels[:, :, 0] = color[0]
        pixels[:, :, 1] = color[1]
        pixels[:, :, 2] = color[2]
        alpha[:, :] = np.frombuffer(mask_bytes, dtype=np.uint8).reshape((cell_h, cell_w)).T
        del pixels, alpha
        return surf
