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

"""BadgeGlyph: a filled circle with a single character centered inside — the
footswitch (A)-(D) / tweak-encoder (1)(2)(3) binding marker
(docs/r4-badge-surfaces.md §5). Unlike the plain alpha-mask glyphs in
circle.py, the character has to be baked into the pixels, so the render is
cached per (char, color, radius) rather than tinted at blit time."""

from functools import lru_cache

import pygame

from uilib.config import Config
from uilib.glyphs.circle import CircleGlyph
from uilib.glyphs.tint import tint_mask
from uilib.misc import get_text_size


@lru_cache(maxsize=32)
def _badge_surface(char: str, color: tuple[int, int, int], radius: int) -> pygame.Surface:
    surf = tint_mask(CircleGlyph(radius).render(), color).copy()  # copy: don't mutate the shared tint cache
    font = Config().get_font("menu_badge")
    if font is None:
        return surf
    d = 2 * radius + 1
    tw, th = get_text_size(char, font)
    asc = int(font.get_sized_ascender())
    prev = font.origin
    font.origin = True
    try:
        font.render_to(surf, ((d - tw) // 2, (d - th) // 2 + asc), char, fgcolor=(255, 255, 255, 255))
    finally:
        font.origin = prev
    return surf


class BadgeGlyph:
    """`Glyph`-shaped (width/height/render()): a colored disc with `char`
    centered in it, in the `footswitch_badge` font. Cheap to construct fresh
    per draw call — the actual pixels are cached by `_badge_surface`."""

    def __init__(self, char: str, color: tuple[int, int, int] = (130, 130, 130), radius: int = 6) -> None:
        self.char = char
        self.color = color
        self._radius = radius

    @property
    def width(self) -> int:
        return 2 * self._radius + 1

    @property
    def height(self) -> int:
        return 2 * self._radius + 1

    def render(self) -> pygame.Surface:
        return _badge_surface(self.char, self.color, self._radius)
