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

"""Filled and ring circle glyphs with analytic anti-aliasing.

Both render as **alpha masks**: white RGB with coverage in the alpha channel.
Callers tint at blit time (see `uilib.icon.Icon._draw` for the
BLEND_RGBA_MULT pattern). This keeps the glyph cache keyed only on geometry,
not colour, and produces genuinely smooth circle edges at small sizes —
`gfxdraw.filled_circle`/`draw.circle` are jaggy or discontinuous at the
6-10px radii the footswitch dots use.

Coverage is sampled with a 1px linear falloff about each analytic boundary.

CircleGlyph — filled disc of radius r:
  Surface (2r+1)×(2r+1), centre at (r, r).
  Blit at (cx - r, cy - r).

RingGlyph — centered-stroke ring, matching the KnobGlyph aesthetic:
  Surface (2*(r+1)+1)×(2*(r+1)+1), centre at (r+1, r+1); ring at distance r.
  The 1px pad gives the outer AA edge room (same convention as KnobGlyph).
  Blit at (cx - half_size, cy - half_size) where half_size = r + 1.
"""

from functools import lru_cache

import numpy as np
import pygame


@lru_cache(maxsize=64)
def _circle_surface(radius: int) -> pygame.Surface:
    """Cached filled-circle alpha mask of size (2r+1)x(2r+1).

    White RGB, coverage in alpha. The circle is centred at (r, r) with
    analytic radius r; coverage = clip(0.5 - |d - r|, 0, 1) sampled at
    pixel corners.
    """
    size = 2 * radius + 1
    xs = np.arange(size)
    ys = np.arange(size)
    X, Y = np.meshgrid(xs, ys)
    d = np.sqrt((X - radius) ** 2 + (Y - radius) ** 2)
    # Filled circle: full coverage inside r, linear 1px AA falloff across
    # the boundary (d in [r-0.5, r+0.5]). Sampled at pixel corners so the
    # circle passes exactly through the corner at distance r.
    cov = np.clip(radius + 0.5 - d, 0.0, 1.0)
    alpha = (cov * 255).astype(np.uint8)

    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    # surfarray uses (W, H) ordering; our arrays are (H, W) so transpose.
    pixels = pygame.surfarray.pixels3d(surf)
    pixels[:, :, 0] = 255
    pixels[:, :, 1] = 255
    pixels[:, :, 2] = 255
    del pixels
    pa = pygame.surfarray.pixels_alpha(surf)
    pa[:] = alpha.T
    del pa  # release the surface lock before returning
    return surf


@lru_cache(maxsize=64)
def _ring_surface(radius: int, ring_half: float) -> pygame.Surface:
    """Cached ring alpha mask, (2*(r+1)+1)×(2*(r+1)+1), centred at (r+1, r+1).

    Centered stroke of half-width ring_half at distance r from the centre.
    Same formula as KnobGlyph: coverage = clip(ring_half + 0.5 - |d - r|, 0, 1).
    """
    half = radius + 1
    size = 2 * half + 1
    xs = np.arange(size)
    ys = np.arange(size)
    X, Y = np.meshgrid(xs, ys)
    d = np.sqrt((X - half) ** 2 + (Y - half) ** 2)
    cov = np.clip(ring_half + 0.5 - np.abs(d - radius), 0.0, 1.0)
    alpha = (cov * 255).astype(np.uint8)

    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pixels = pygame.surfarray.pixels3d(surf)
    pixels[:, :, 0] = 255
    pixels[:, :, 1] = 255
    pixels[:, :, 2] = 255
    del pixels
    pa = pygame.surfarray.pixels_alpha(surf)
    pa[:] = alpha.T
    del pa
    return surf


class CircleGlyph:
    """Filled circle with analytic anti-aliased edges.

    `render()` returns a `(2r+1)x(2r+1)` RGBA **alpha mask** (white RGB,
    coverage in alpha). Callers tint at blit time via BLEND_RGBA_MULT.
    Blit at (cx - radius, cy - radius) to centre on (cx, cy).
    """

    def __init__(self, radius: int) -> None:
        self._radius = int(radius)

    @property
    def radius(self) -> int:
        return self._radius

    @property
    def width(self) -> int:
        return 2 * self._radius + 1

    @property
    def height(self) -> int:
        return 2 * self._radius + 1

    def render(self) -> pygame.Surface:
        return _circle_surface(self._radius)


class RingGlyph:
    """Centered-stroke ring matching the KnobGlyph aesthetic.

    Stroke of half-width `ring_half` (default 0.75 → 1.5px visual, same as
    KnobGlyph) centred at `radius` pixels from the surface centre.

    `render()` returns a `(2*(r+1)+1)×(2*(r+1)+1)` RGBA **alpha mask**.
    Callers tint at blit time via BLEND_RGBA_MULT.
    Blit at (cx - half_size, cy - half_size) to centre on (cx, cy).
    """

    def __init__(self, radius: int, ring_half: float = 0.75) -> None:
        self._radius = int(radius)
        self._ring_half = ring_half

    @property
    def radius(self) -> int:
        return self._radius

    @property
    def half_size(self) -> int:
        return self._radius + 1

    @property
    def width(self) -> int:
        return 2 * self.half_size + 1

    @property
    def height(self) -> int:
        return 2 * self.half_size + 1

    def render(self) -> pygame.Surface:
        return _ring_surface(self._radius, self._ring_half)
