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

import pygame

from uilib.glyphs import DEFAULT_COLOR as _DEFAULT_COLOR
from uilib.glyphs import FONTS_DIR as _FONTS_DIR
from uilib.pygame_init import font as _make_font


class PillGlyph:
    """Rounded-rectangle badge with a short label inside."""

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
        # Center the label's ink rect (not line box) inside the pill. With
        # origin=False, render_to's pen position is the top-left of the ink
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
