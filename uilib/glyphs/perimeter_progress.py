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

"""Chamfered perimeter used as a progress track.

Renders an **alpha mask** (white RGB, coverage in alpha) of the polygonal path
from `start` to `end` measured as arclength around a chamfered rectangle,
clockwise from top-centre. `segments` notches the track at each 1/n boundary,
so a 4-bar loop reads as four angular arcs rather than a rounded box.

The path is an analytic distance field over straight vector edges. Geometry is
cached per (size, chamfer, thickness); `render` is not, because a progress
sweep visits every pixel step.

Unlike the disc glyphs this is sized to a box, not a radius: blit at the box's
top-left, no centring offset.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
import pygame


@lru_cache(maxsize=16)
def _geometry(width: int, height: int, radius: int, thickness: float) -> tuple[np.ndarray, np.ndarray, float]:
    """Return coverage, normalized path position, and polygon perimeter."""
    w = float(width)
    h = float(height)
    chamfer = min(max(float(radius), 0.0), w / 2.0, h / 2.0)
    points = (
        (w / 2.0, 0.0),
        (w - chamfer, 0.0),
        (w, chamfer),
        (w, h - chamfer),
        (w - chamfer, h),
        (chamfer, h),
        (0.0, h - chamfer),
        (0.0, chamfer),
        (chamfer, 0.0),
    )

    x = np.arange(width, dtype=float) + 0.5
    y = np.arange(height, dtype=float) + 0.5
    X, Y = np.meshgrid(x, y)
    best = np.full((height, width), np.inf)
    position = np.zeros((height, width), dtype=float)
    offset = 0.0

    for start, end in zip(points, points[1:] + points[:1]):
        x0, y0 = start
        x1, y1 = end
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy)
        if length == 0.0:
            continue
        u = np.clip(((X - x0) * dx + (Y - y0) * dy) / (length * length), 0.0, 1.0)
        nearest_x = x0 + u * dx
        nearest_y = y0 + u * dy
        distance = np.hypot(X - nearest_x, Y - nearest_y)
        closer = distance < best
        best = np.where(closer, distance, best)
        position = np.where(closer, offset + u * length, position)
        offset += length

    coverage = np.clip(thickness / 2.0 + 0.5 - best, 0.0, 1.0)
    perimeter = offset
    return coverage, np.mod(position / perimeter, 1.0), perimeter


class PerimeterProgressGlyph:
    """Progress track around a chamfered rectangle.

    `render()` returns an alpha mask the size of the box; blit it at the box's
    top-left.
    """

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
