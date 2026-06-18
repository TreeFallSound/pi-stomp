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

from uilib.glyphs import DEFAULT_COLOR as _DEFAULT_COLOR


@lru_cache(maxsize=32)
def _tl_arc_surface(r: int, color: tuple[int, int, int]) -> pygame.Surface:
    """Cached top-left arc surface of size (r+1) x (r+1), RGBA, color baked in.

    Samples at pixel corners (integer coordinates), not pixel centers: the
    arc circle (center (r,r), radius r) passes exactly through the corner
    points (r,0) and (0,r), which are the junctions with the keycap's
    straight top and left edges. Sampling there makes those endpoints fully
    lit so the arc connects seamlessly with the 1px lines.
    """
    size = r + 1
    xs = np.arange(size)
    ys = np.arange(size)
    X, Y = np.meshgrid(xs, ys)
    d = np.sqrt((X - r) ** 2 + (Y - r) ** 2)
    cov = np.clip(1.0 - np.abs(d - r), 0.0, 1.0)
    alpha = (cov * 255).astype(np.uint8)

    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    # surfarray uses (W, H) ordering; our arrays are (H, W) so transpose.
    pixels = pygame.surfarray.pixels3d(surf)
    pixels[:, :, 0] = color[0]
    pixels[:, :, 1] = color[1]
    pixels[:, :, 2] = color[2]
    del pixels
    pa = pygame.surfarray.pixels_alpha(surf)
    pa[:] = alpha.T
    del pa  # release the surface lock before returning
    return surf


class KeycapCornerGlyph:
    """Top-left rounded-corner arc for a footswitch keycap outline.

    `render()` returns an (r+1) x (r+1) RGBA surface with the arc drawn on a
    transparent background. The stroke is 1px wide, anti-aliased via an
    analytic distance falloff (not supersampled), so it stays continuous
    at the 45° diagonal where `gfxdraw.aacircle` breaks down.

    For the top-right corner, flip the result horizontally:
    `pygame.transform.flip(glyph.render(), True, False)`. The flip lands the
    arc's endpoint at pixel (0, r) — the junction with the right edge.
    """

    def __init__(self, radius: int, color: tuple[int, int, int] = _DEFAULT_COLOR) -> None:
        self._r = int(radius)
        self._color = color
        self._size = self._r + 1

    @property
    def width(self) -> int:
        return self._size

    @property
    def height(self) -> int:
        return self._size

    def render(self) -> pygame.Surface:
        return _tl_arc_surface(self._r, self._color)
