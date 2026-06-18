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
        d.rectangle([body_x, body_y, body_x + body_w - 1, body_y + body_h - 1], outline=255, width=1)

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
