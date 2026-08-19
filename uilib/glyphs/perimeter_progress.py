# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Rounded-rectangle perimeter used as a progress track.

Renders an **alpha mask** (white RGB, coverage in alpha) of the arc from
`start` to `end` measured as arclength around a rounded rect, clockwise from
top-centre. `segments` notches the track at each 1/n boundary, so a 4-bar loop
reads as four arcs rather than one continuous stroke.

Geometry is cached per (size, radius, thickness); `render` is not — a mask is
~2700 pixels of numpy and a progress sweep visits every pixel step, so caching
the masks would cost megabytes to save microseconds.

Unlike the disc glyphs this is sized to a box, not a radius: blit at the box's
top-left, no centring offset.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
import pygame

_TWO_PI = 2.0 * math.pi


@lru_cache(maxsize=16)
def _geometry(width: int, height: int, radius: int, thickness: float) -> tuple[np.ndarray, np.ndarray, float]:
    """(coverage, t, perimeter) for a rounded-rect outline.

    `coverage` is the anti-aliased stroke band; `t` is each pixel's position
    in [0, 1) along the path, taken at the nearest point on it. Pixels well
    inside the shape have no nearest point in any meaningful sense, but their
    coverage is 0, so `t` there is arbitrary rather than wrong.
    """
    a = width / 2.0
    b = height / 2.0
    r = min(float(radius), a, b)
    ex = a - r  # half-length of the horizontal straights
    ey = b - r

    quarter = 0.5 * math.pi * r
    perimeter = 4.0 * ex + 4.0 * ey + _TWO_PI * r

    x = np.arange(width, dtype=float) + 0.5
    y = np.arange(height, dtype=float) + 0.5
    X, Y = np.meshgrid(x, y)
    dx = X - a
    dy = Y - b

    # Nearest point on the inner rect; the path is that point pushed out by r.
    ix = np.clip(dx, -ex, ex)
    iy = np.clip(dy, -ey, ey)
    vx = dx - ix
    vy = dy - iy
    dist = np.hypot(vx, vy)
    coverage = np.clip(thickness / 2.0 + 0.5 - np.abs(dist - r), 0.0, 1.0)

    # Arclength offsets, clockwise from top-centre: the top edge is split so
    # t=0 lands mid-top rather than on a corner.
    o_tr_arc = ex
    o_right = o_tr_arc + quarter
    o_br_arc = o_right + 2.0 * ey
    o_bottom = o_br_arc + quarter
    o_bl_arc = o_bottom + 2.0 * ex
    o_left = o_bl_arc + quarter
    o_tl_arc = o_left + 2.0 * ey
    o_top_left = o_tl_arc + quarter

    theta = np.arctan2(vy, vx)
    past_x = np.abs(dx) > ex
    past_y = np.abs(dy) > ey
    right = dx > 0
    below = dy > 0

    s = np.where(right, dx, o_top_left + ex + dx)  # top edge, split at centre
    s = np.where(past_y & below, o_bottom + (ex - dx), s)
    s = np.where(past_x & ~past_y & right, o_right + (dy + ey), s)
    s = np.where(past_x & ~past_y & ~right, o_left + (ey - dy), s)
    s = np.where(past_x & past_y & right & ~below, o_tr_arc + r * (theta + 0.5 * math.pi), s)
    s = np.where(past_x & past_y & right & below, o_br_arc + r * theta, s)
    s = np.where(past_x & past_y & ~right & below, o_bl_arc + r * (theta - 0.5 * math.pi), s)
    s = np.where(past_x & past_y & ~right & ~below, o_tl_arc + r * (theta + math.pi), s)

    return coverage, np.mod(s / perimeter, 1.0), perimeter


class PerimeterProgressGlyph:
    """Progress track around a rounded rect. `render()` returns an alpha mask
    the size of the box; blit it at the box's top-left."""

    def __init__(self, width: int, height: int, radius: int, thickness: float = 2.0) -> None:
        self._width = int(width)
        self._height = int(height)
        self._radius = int(radius)
        self._thickness = float(thickness)

    @property
    def perimeter(self) -> float:
        """Path length in pixels — the natural quantum for a progress step."""
        return _geometry(self._width, self._height, self._radius, self._thickness)[2]

    def render(self, start: float, end: float, segments: int = 0, gap: float = 3.0) -> pygame.Surface:
        """Mask of the arc [start, end] in turns, wrapping past 1.

        `segments` > 1 opens a `gap`-pixel notch at every 1/segments boundary.
        """
        coverage, t, perimeter = _geometry(self._width, self._height, self._radius, self._thickness)

        span = end - start
        if span >= 1.0:
            select = np.ones_like(t)
        elif span <= 0.0:
            select = np.zeros_like(t)
        else:
            behind = np.mod(t - start, 1.0)
            select = np.clip((span - behind) * perimeter + 0.5, 0.0, 1.0)
            if start != 0.0:
                select = select * np.clip(behind * perimeter + 0.5, 0.0, 1.0)

        if segments > 1:
            to_boundary = np.abs(np.mod(t * segments + 0.5, 1.0) - 0.5) * perimeter / segments
            select = select * np.clip(to_boundary - gap / 2.0 + 0.5, 0.0, 1.0)

        alpha = np.clip(coverage * select * 255.0, 0.0, 255.0).astype(np.uint8)

        surf = pygame.Surface((self._width, self._height), pygame.SRCALPHA)
        pixels = pygame.surfarray.pixels3d(surf)
        pixels[:, :, 0] = 255
        pixels[:, :, 1] = 255
        pixels[:, :, 2] = 255
        del pixels
        pa = pygame.surfarray.pixels_alpha(surf)
        pa[:] = alpha.T
        del pa
        return surf
