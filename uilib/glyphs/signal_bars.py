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

import numpy as np
import pygame
from PIL import Image, ImageDraw

from uilib.glyphs import DEFAULT_COLOR as _DEFAULT_COLOR


class SignalBarsGlyph:
    """Cellphone-style signal strength: slices of a right triangle. Bar 0 is
    a triangle (left edge zero-height); bars 1..n are trapezoids whose tops
    follow a single continuous hypotenuse spanning the full glyph width.
    Bars `[0:level]` are filled; the rest are outlined.

    Rendered via 4x supersampling + smoothscale for anti-aliased edges.
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
        alpha[:, :] = np.frombuffer(mask_bytes, dtype=np.uint8).reshape((cell_h, cell_w)).T
        del pixels, alpha  # release surface locks before returning
        return surf
