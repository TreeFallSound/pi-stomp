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

"""Colorizing white alpha-mask glyphs.

Glyph caches are keyed on geometry only, so masks come back white and the caller
tints at blit time. The tint is cached too: mask surfaces are `lru_cache`d (so
their identity is stable) and the colors come from small constant sets, so a
handful of entries covers every footswitch dot, icon, EQ node and reticule.

The returned surface is shared — blit it, never mutate it.
"""

from functools import lru_cache

import pygame

from common.color import ColorRGB
from uilib.paint import ColorLike, as_color


@lru_cache(maxsize=128)
def _tinted(mask: pygame.Surface, color: ColorRGB) -> pygame.Surface:
    tinted = mask.copy()
    color_surf = pygame.Surface(mask.get_size(), pygame.SRCALPHA)
    color_surf.fill(color)
    tinted.blit(color_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return tinted


def tint_mask(mask: pygame.Surface, color: ColorLike) -> pygame.Surface:
    """Tint a white alpha-mask glyph into `color` (BLEND_RGBA_MULT on a copy)."""
    c = as_color(color)
    return _tinted(mask, (c.r, c.g, c.b))
