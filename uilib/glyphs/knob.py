# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-Stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Knob glyph for the analog-controls strip on the v3 LCD.

A hollow ring (outlined circle) with a pointer line from the center to
the upper-right, evoking a rotary potentiometer indicator. Both shapes are
computed analytically with numpy so the edges are genuinely smooth at small
sizes — `gfxdraw`/`draw.circle` are jaggy or discontinuous at the 13px scale
this icon renders at.

The glyph renders as an **alpha mask**: white RGB with coverage in the alpha
channel. Callers tint at blit time (see `Icon._draw`, which multiplies a
solid colour fill into the mask via `BLEND_RGBA_MULT`). This keeps the glyph
cache keyed only on size, not colour.
"""

from functools import lru_cache

import numpy as np
import pygame

_WHITE = (255, 255, 255)


def _segment_coverage(X: np.ndarray, Y: np.ndarray,
                      x0: float, y0: float, x1: float, y1: float,
                      half_width: float) -> np.ndarray:
    """Anti-aliased coverage of a 1-D line segment, sampled at pixel corners,
    with **rectangular** (butt-cap) ends.

    `half_width` is the half-thickness of the stroke. Coverage is the product
    of two independent 1px cone falloffs:
      * perpendicular to the spine (the stroke's thickness), and
      * along the spine (the segment's endpoints),
    so the result is a filled rectangle with 1px AA on all four sides and
    sharp square corners — no rounded caps. The `+0.5` accounts for
    pixel-corner sampling so a stroke exactly `half_width` thick comes out
    at full coverage on the spine pixels.
    """
    dx = x1 - x0
    dy = y1 - y0
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        # Degenerate: a point. Treat as a square of side 2*half_width.
        d_perp = np.sqrt((X - x0) ** 2 + (Y - y0) ** 2)
        return np.clip(half_width + 0.5 - d_perp, 0.0, 1.0)
    # Perpendicular distance to the infinite line (no endpoint clamping).
    t_unclamped = ((X - x0) * dx + (Y - y0) * dy) / L2
    perp = np.abs((X - x0) * dy - (Y - y0) * dx) / np.sqrt(L2)
    cov_perp = np.clip(half_width + 0.5 - perp, 0.0, 1.0)
    # Along-spine distance from the nearest endpoint, clamped to [0,1]
    # projection so pixels past either end see the cap edge, not the spine.
    L = np.sqrt(L2)
    t = np.clip(t_unclamped, 0.0, 1.0)
    along = np.abs(t - t_unclamped) * L
    cov_along = np.clip(half_width + 0.5 - along, 0.0, 1.0)
    return cov_perp * cov_along


@lru_cache(maxsize=32)
def _knob_surface(size: int) -> pygame.Surface:
    """Cached knob alpha-mask surface of size×size (white RGB, coverage in A).

    A hollow ring (outlined circle) with a pointer line from the center to
    the upper-right — the classic potentiometer indicator. Both shapes are
    analytically anti-aliased.
    """
    cx = cy = (size - 1) / 2.0
    radius = (size - 2) / 2.0  # leave a 1px margin so AA edge isn't clipped
    ring_half = 0.75  # half-width of the ring stroke (1.5px visual)
    xs = np.arange(size)
    ys = np.arange(size)
    X, Y = np.meshgrid(xs, ys)
    d = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    # Ring: 1px stroke at `radius`, coverage falls off linearly with |d - radius|.
    ring = np.clip(ring_half + 0.5 - np.abs(d - radius), 0.0, 1.0)
    # Pointer: from center toward upper-right (classic pot indicator).
    # Endpoint sits just inside the ring so the pointer reads as a notch.
    end = cx + radius * 0.75
    ptr = _segment_coverage(X, Y, cx, cy, end, cx - radius * 0.75,
                             half_width=0.7)
    total = np.maximum(ring, ptr)
    alpha = (total * 255).astype(np.uint8)

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


class KnobGlyph:
    """Rotary knob: a hollow ring (outlined circle) with an upper-right
    pointer indicator.

    `render()` returns a `size`×`size` RGBA **alpha mask** (white RGB,
    coverage in alpha). Callers tint at blit time. The ring is an
    analytically anti-aliased circle outline; the pointer is an
    anti-aliased line segment from the center to the upper-right,
    evoking a potentiometer's indicator notch.
    """

    def __init__(self, size: int) -> None:
        self._size = int(size)

    @property
    def width(self) -> int:
        return self._size

    @property
    def height(self) -> int:
        return self._size

    def render(self) -> pygame.Surface:
        return _knob_surface(self._size)