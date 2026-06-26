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

"""Arc-ring glyph with analytic anti-aliasing.

A thick ring arc from 7-o'clock clockwise (210° → 5-o'clock, 300° travel),
split at value position t ∈ [0, 1] between a filled colour and an empty
colour. A small tip dot marks the current position.

The glyph renders to an SRCALPHA surface. Blit at (cx - half_size, cy -
half_size) to centre on (cx, cy). The radial/angular grids are built once
in __init__; only the per-t compositing runs in render().
"""

from __future__ import annotations

import math

import numpy as np
import pygame

_START_DEG = 210.0  # arc start — 7-o'clock
_SWEEP_DEG = 300.0  # total arc travel
_AA_DEG = 1.5       # angular AA falloff (≈1 px at r=35)

ColorRGB = tuple[int, int, int]


class ArcRingGlyph:
    """Rotary-parameter arc ring with analytic AA.

    Blit render() at (cx - half_size, cy - half_size) to centre on (cx, cy).
    """

    def __init__(self, radius: int, ring_half: float = 4.5, tip_radius: float = 3.5) -> None:
        self._r = int(radius)
        self._tip_radius = float(tip_radius)
        margin = math.ceil(max(ring_half, tip_radius)) + 1
        self._half = self._r + margin
        size = 2 * self._half + 1
        self._size = size

        xs = np.arange(size, dtype=float)
        ys = np.arange(size, dtype=float)
        X, Y = np.meshgrid(xs, ys)
        self._X = X
        self._Y = Y
        dx = X - self._half
        dy = Y - self._half
        d = np.sqrt(dx ** 2 + dy ** 2)

        self._ring_cov: np.ndarray = np.clip(
            ring_half + 0.5 - np.abs(d - self._r), 0.0, 1.0
        )
        # Clockwise-from-top angle [0, 360), shifted so _START_DEG maps to 0
        angle = np.degrees(np.arctan2(dx, -dy)) % 360.0
        self._shifted: np.ndarray = (angle - _START_DEG) % 360.0

    @property
    def half_size(self) -> int:
        return self._half

    @property
    def size(self) -> int:
        return self._size

    def render(
        self,
        t: float,
        filled_color: ColorRGB,
        empty_color: ColorRGB,
        tip_color: ColorRGB,
    ) -> pygame.Surface:
        """Return an SRCALPHA surface with the arc drawn in two colours + tip dot."""
        t = max(0.0, min(1.0, t))
        sweep = t * _SWEEP_DEG
        aa = _AA_DEG
        shifted = self._shifted
        ring_cov = self._ring_cov

        # Filled arc: shifted in [0, sweep]
        filled_cov = (
            ring_cov
            * np.clip(shifted / aa + 0.5, 0.0, 1.0)
            * np.clip((sweep - shifted) / aa + 0.5, 0.0, 1.0)
        )
        # Empty arc: shifted in [sweep, 300]
        empty_cov = (
            ring_cov
            * np.clip((shifted - sweep) / aa + 0.5, 0.0, 1.0)
            * np.clip((_SWEEP_DEG - shifted) / aa + 0.5, 0.0, 1.0)
        )

        # Tip dot at the current value position on the ring
        tip_deg = _START_DEG + sweep
        tip_rad = math.radians(tip_deg)
        tip_cx = self._half + self._r * math.sin(tip_rad)
        tip_cy = self._half - self._r * math.cos(tip_rad)
        tip_d = np.sqrt((self._X - tip_cx) ** 2 + (self._Y - tip_cy) ** 2)
        tip_cov = np.clip(self._tip_radius + 0.5 - tip_d, 0.0, 1.0)

        fr, fg_c, fb = filled_color
        er, eg, eb = empty_color
        tr, tg, tb = tip_color

        R = np.clip(filled_cov * fr + empty_cov * er + tip_cov * tr, 0, 255).astype(np.uint8)
        G = np.clip(filled_cov * fg_c + empty_cov * eg + tip_cov * tg, 0, 255).astype(np.uint8)
        B = np.clip(filled_cov * fb + empty_cov * eb + tip_cov * tb, 0, 255).astype(np.uint8)
        A = np.clip((filled_cov + empty_cov + tip_cov) * 255, 0, 255).astype(np.uint8)

        surf = pygame.Surface((self._size, self._size), pygame.SRCALPHA)
        pix = pygame.surfarray.pixels3d(surf)
        pix[:, :, 0] = R.T
        pix[:, :, 1] = G.T
        pix[:, :, 2] = B.T
        del pix
        pa = pygame.surfarray.pixels_alpha(surf)
        pa[:] = A.T
        del pa
        return surf
