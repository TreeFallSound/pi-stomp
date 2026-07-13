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

"""BadgeGlyph: a filled white circle with a single black character centered
inside — a small marker glyph any widget can carry (see uilib/README.md's
Badges section). One fixed appearance everywhere it's used, so the marker
itself is what's consistent, not incidental panel coloring. Unlike the plain
alpha-mask glyphs in circle.py, the character has to be baked into the
pixels, so the render is cached per (char, radius) rather than tinted at
blit time."""

from functools import lru_cache

import pygame

from uilib.config import Config
from uilib.glyphs.circle import CircleGlyph
from uilib.glyphs.tint import tint_mask
from uilib.misc import get_text_size

_FILL = (255, 255, 255)
_TEXT = (0, 0, 0, 255)


@lru_cache(maxsize=32)
def _badge_surface(char: str, radius: int) -> pygame.Surface:
    surf = tint_mask(CircleGlyph(radius).render(), _FILL).copy()  # copy: don't mutate the shared tint cache
    font = Config().get_font("menu_badge")
    if font is None:
        return surf
    d = 2 * radius + 1
    tw, th = get_text_size(char, font)
    asc = int(font.get_sized_ascender())
    prev = font.origin
    font.origin = True
    try:
        font.render_to(surf, ((d - tw) // 2, (d - th) // 2 + asc), char, fgcolor=_TEXT)
    finally:
        font.origin = prev
    return surf


class BadgeGlyph:
    """`Glyph`-shaped (width/height/render()): a white disc with `char`
    centered in it in black, in the `menu_badge` font. Cheap to construct
    fresh per draw call — the actual pixels are cached by `_badge_surface`."""

    def __init__(self, char: str, radius: int = 6) -> None:
        self.char = char
        self._radius = radius

    @property
    def width(self) -> int:
        return 2 * self._radius + 1

    @property
    def height(self) -> int:
        return 2 * self._radius + 1

    def render(self) -> pygame.Surface:
        return _badge_surface(self.char, self._radius)
