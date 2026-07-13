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
from PIL import Image

from uilib.config import Config
from uilib.glyphs.circle import CircleGlyph
from uilib.glyphs.tint import tint_mask
from uilib.misc import get_text_size

_FILL = (255, 255, 255)
_TEXT = (0, 0, 0, 255)

# Sub-pixel hinting at this font size leaves a few glyphs visibly off the
# advance-width center; nudge those by eye, in half-pixel units (1 == 0.5px,
# fractional values allowed — e.g. 0.5 == a quarter pixel). Rendered via
# supersampling (see _SS below) so these are real sub-pixel shifts.
_X_NUDGE_HALF = {"A": 0.5, "C": -1, "D": 1, "3": 1}

# Supersample factor for the text layer only: render at _SS× size/position,
# then downscale, so a half-pixel nudge is an actual sub-pixel shift instead
# of rounding to the nearest whole pixel. Cached per (char, radius), so this
# costs nothing at draw time.
_SS = 4


def _lanczos_downscale(surf: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
    # pygame.transform has no Lanczos filter — smoothscale/rotozoom are both
    # box/bilinear and visibly blur glyph strokes at this radius. Route
    # through Pillow (already a dependency) for a sharper resample.
    img = Image.frombytes("RGBA", surf.get_size(), pygame.image.tobytes(surf, "RGBA"))
    img = img.resize(size, Image.Resampling.LANCZOS)
    return pygame.image.frombytes(img.tobytes(), size, "RGBA")


@lru_cache(maxsize=32)
def _badge_surface(char: str, radius: int) -> pygame.Surface:
    surf = tint_mask(CircleGlyph(radius).render(), _FILL).copy()  # copy: don't mutate the shared tint cache
    font = Config().get_font("menu_badge")
    if font is None:
        return surf
    d = 2 * radius + 1
    base_size = font.size if isinstance(font.size, (int, float)) else font.size[0]
    big_size = base_size * _SS
    tw, th = get_text_size(char, font, size=big_size)
    asc = int(font.get_sized_ascender(big_size))
    nudge = round(_X_NUDGE_HALF.get(char, 0) * _SS / 2)

    text_layer = pygame.Surface((d * _SS, d * _SS), pygame.SRCALPHA)
    prev = font.origin
    font.origin = True
    try:
        x = (d * _SS - tw) // 2 + nudge
        y = (d * _SS - th) // 2 + asc
        font.render_to(text_layer, (x, y), char, fgcolor=_TEXT, size=big_size)  # pyright: ignore[reportCallIssue]
    finally:
        font.origin = prev
    surf.blit(_lanczos_downscale(text_layer, (d, d)), (0, 0))
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
