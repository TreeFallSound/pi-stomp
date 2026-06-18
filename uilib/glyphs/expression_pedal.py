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

"""Expression pedal glyph for the analog-controls strip on the v3 LCD.

A rocker-pedal silhouette: a diagonal rocker arm rising from the lower-left
pivot to the upper-right toe, sitting on a horizontal base bar. Both shapes
are computed analytically with numpy for genuine anti-aliasing at the 13px
scale — pygame's line/circle primitives are jaggy at this size.

The glyph renders as an **alpha mask**: white RGB with coverage in the alpha
channel. Callers tint at blit time (see `Icon._draw`, which multiplies a
solid colour fill into the mask via `BLEND_RGBA_MULT`). This keeps the glyph
cache keyed only on size, not colour.
"""

from functools import lru_cache

import numpy as np
import pygame

from uilib.glyphs.knob import _segment_coverage

# --- Geometry knobs ---
# The pedal is two strokes from a single pivot near the bottom-left: a thick
# horizontal base and a thinner diagonal riser. All in fractional pixels
# relative to `size` unless noted.
_MARGIN = 1.5  # pivot inset from the left and bottom edges (px)
_RISER_LENGTH = 0.85  # riser length (fraction of size); clamped to bounds
_RISER_ANGLE = 38.0  # degrees above horizontal (toe rises up-right)
_RISER_THICKNESS = 1.8  # full thickness of the riser stroke (px)
_BASE_THICKNESS = 3.8  # full thickness of the base stroke (px)
_RISER_Y_ADJUST = -1.8  # nudge the riser pivot up/down (px) vs the base pivot


@lru_cache(maxsize=32)
def _pedal_surface(size: int) -> pygame.Surface:
    """Cached expression-pedal alpha-mask surface of size×size (white RGB,
    coverage in A)."""
    xs = np.arange(size)
    ys = np.arange(size)
    X, Y = np.meshgrid(xs, ys)

    # Shared pivot: bottom-left, inset by _MARGIN from both edges.
    pivot_x = _MARGIN
    pivot_y = (size - 1) - _MARGIN

    # Base: horizontal stroke from the pivot to the right edge.
    base_end_x = (size - 1) - _MARGIN
    base = _segment_coverage(X, Y, pivot_x, pivot_y, base_end_x, pivot_y, half_width=_BASE_THICKNESS / 2)

    # Riser: diagonal from the pivot (optionally nudged) up-right at
    # _RISER_ANGLE. Length clamped so the toe stays in bounds.
    riser_pivot_y = pivot_y + _RISER_Y_ADJUST
    angle_rad = np.radians(_RISER_ANGLE)
    dx = np.cos(angle_rad)
    dy = -np.sin(angle_rad)  # screen y is down
    desired_len = _RISER_LENGTH * size
    # Max travel before hitting the right or top edge (with _MARGIN inset).
    max_dx = ((size - 1) - _MARGIN - pivot_x) / dx if dx > 1e-6 else np.inf
    max_dy = (riser_pivot_y - _MARGIN) / -dy if dy < -1e-6 else np.inf
    length = min(max_dx, max_dy, desired_len)
    toe_x = pivot_x + length * dx
    toe_y = riser_pivot_y + length * dy
    riser = _segment_coverage(X, Y, pivot_x, riser_pivot_y, toe_x, toe_y, half_width=_RISER_THICKNESS / 2)

    total = np.maximum(base, riser)
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


class ExpressionPedalGlyph:
    """Expression pedal: diagonal rocker arm on a horizontal base bar.

    `render()` returns a `size`×`size` RGBA **alpha mask** (white RGB,
    coverage in alpha). Callers tint at blit time. The rocker rises from a
    lower-left pivot to an upper-right toe; the base bar sits along the
    bottom. Both are analytically anti-aliased.
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
        return _pedal_surface(self._size)
