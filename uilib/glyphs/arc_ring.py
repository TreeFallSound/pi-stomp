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

With ``flip_v=True`` the rendered image is reflected vertically so the gap
sits at the **top** (12-o'clock): ``t=0`` fills from upper-left, ``t=1`` from
upper-right — the intuitive min-left/max-right direction, leaving the top gap
free for a label.

The glyph renders to an SRCALPHA surface. Blit at (cx - half_size, cy -
half_size) to centre on (cx, cy). Geometry is precomputed in __init__ over the
ink band only; render() is cached.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
import pygame

from common.color import ColorRGB

_START_DEG = 210.0  # arc start — 7-o'clock
_SWEEP_DEG = 300.0  # total arc travel
_AA_DEG = 1.5       # angular AA falloff (≈1 px at r=35)

# Selection sandwich: an inset border tracing the filled sector's outer contour
# (outer edge + caps), so a selected dial reads in the same visual language as
# every other value marker. From the fill inward it stacks black then yellow at
# the value handle's own weights — the arc's edge becomes a distance field:
# original colour, black rim, yellow rim.
_SEL_BLACK = 2.0    # black band width, matching the handle's eraser annulus
_SEL_YELLOW = 1.5   # yellow band width, matching the handle's halo stroke

__all__ = ["ArcRingGlyph", "ColorRGB"]


class ArcRingGlyph:
    """Rotary-parameter arc ring with analytic AA.

    Blit render() at (cx - half_size, cy - half_size) to centre on (cx, cy).
    """

    def __init__(
        self, radius: int, ring_half: float = 4.5, flip_v: bool = False
    ) -> None:
        self._r = int(radius)
        self._ring_half = float(ring_half)
        self._flip_v = bool(flip_v)
        margin = math.ceil(ring_half) + 1
        self._half = self._r + margin
        size = 2 * self._half + 1
        self._size = size

        xs = np.arange(size, dtype=float)
        X, Y = np.meshgrid(xs, xs)
        dx = X - self._half
        dy = Y - self._half
        d = np.sqrt(dx ** 2 + dy ** 2)

        ring_cov = np.clip(ring_half + 0.5 - np.abs(d - self._r), 0.0, 1.0)
        # Clockwise-from-top angle [0, 360), shifted so _START_DEG maps to 0
        angle = np.degrees(np.arctan2(dx, -dy)) % 360.0
        shifted = (angle - _START_DEG) % 360.0

        # Keep only the annulus the ring stroke can reach — a third of the
        # grid — so render() works on a ~2k vector, not size². Pixels outside
        # it are transparent under the full-grid formula anyway.
        reach = ring_half + 1.0
        rows, cols = np.nonzero(np.abs(d - self._r) <= reach)
        self._ring_cov: np.ndarray = ring_cov[rows, cols]
        self._shifted: np.ndarray = shifted[rows, cols]
        # Signed radial offset from the track centreline, and the pixel radius —
        # both needed by the selection sandwich to measure inset depth from the
        # outer edge and to convert an angular gap to arc length at the cap.
        self._dr: np.ndarray = (d - self._r)[rows, cols]
        self._d: np.ndarray = d[rows, cols]

        # Row-major destination index, with flip_v folded in so the reflection is
        # free at render time. Packing bytes for image.frombuffer beats scattering
        # into a locked surfarray view by ~3x.
        iy = (size - 1 - rows) if self._flip_v else rows
        self._lin: np.ndarray = iy.astype(np.intp) * size + cols.astype(np.intp)
        # Never cleared: the index set is fixed and every render rewrites all of it.
        self._rgba: np.ndarray = np.zeros((size * size, 4), dtype=np.uint8)
        self._sel_rgba: np.ndarray = np.zeros((size * size, 4), dtype=np.uint8)

    @property
    def half_size(self) -> int:
        return self._half

    @property
    def ring_half(self) -> float:
        return self._ring_half

    @property
    def size(self) -> int:
        return self._size

    def tip_center(self, t: float) -> tuple[float, float]:
        """(x, y) of the value position on the ring for parameter ``t``.

        Honors ``flip_v`` so consumers computing incremental dirty rects don't
        have to re-derive the arc geometry.
        """
        t = max(0.0, min(1.0, t))
        rad = math.radians(_START_DEG + t * _SWEEP_DEG)
        x = self._half + self._r * math.sin(rad)
        cos = self._r * math.cos(rad)
        y = self._half + cos if self._flip_v else self._half - cos
        return (x, y)

    # Keyed on the glyph too, so it pins self — fine, glyphs outlive their panel.
    # A dial repaints far more often than its value changes (any sibling cell going
    # dirty repaints the whole column), so most calls re-ask for the same t.
    @lru_cache(maxsize=64)
    def render(
        self,
        t: float,
        filled_color: ColorRGB,
        empty_color: ColorRGB,
    ) -> pygame.Surface:
        """Arc in two colours, on an SRCALPHA surface. The value marker (bubble)
        is composed by the caller at the tip position — see ``tip_center``.

        The surface is shared — blit it, never mutate it.
        """
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

        fr, fg_c, fb = filled_color
        er, eg, eb = empty_color

        R = np.clip(filled_cov * fr + empty_cov * er, 0, 255).astype(np.uint8)
        G = np.clip(filled_cov * fg_c + empty_cov * eg, 0, 255).astype(np.uint8)
        B = np.clip(filled_cov * fb + empty_cov * eb, 0, 255).astype(np.uint8)
        A = np.clip((filled_cov + empty_cov) * 255, 0, 255).astype(np.uint8)

        lin = self._lin
        rgba = self._rgba
        rgba[lin, 0] = R
        rgba[lin, 1] = G
        rgba[lin, 2] = B
        rgba[lin, 3] = A
        return pygame.image.frombuffer(rgba.tobytes(), (self._size, self._size), "RGBA")

    @lru_cache(maxsize=64)
    def render_halo(self, t: float, color: ColorRGB) -> pygame.Surface:
        """Selection sandwich: an overlay for the *filled* sector [0, t] whose
        outer contour (outer edge + start/end caps) insets into a distance field
        — original colour, then a black rim, then a ``color`` rim at the edge. The
        tip cap runs under the value handle, which caps it, so the caller pastes
        this between the ring and the handle. Blit like render().

        The surface is shared — blit it, never mutate it.
        """
        t = max(0.0, min(1.0, t))
        sweep = t * _SWEEP_DEG
        aa = _AA_DEG
        shifted = self._shifted

        # Filled-sector silhouette (same AA'd coverage as render()'s filled arc):
        # the overlay never spills past it.
        fill_cov = (
            self._ring_cov
            * np.clip(shifted / aa + 0.5, 0.0, 1.0)
            * np.clip((sweep - shifted) / aa + 0.5, 0.0, 1.0)
        )

        # Inset depth from the outer contour: radial to the outer edge, angular
        # (as arc length) to the nearest cap, whichever is closer. The inner edge
        # is deliberately excluded, so the original colour survives along it.
        radial = np.clip(self._ring_half - self._dr, 0.0, None)
        cap_gap = np.minimum(shifted, sweep - shifted)
        angular = np.radians(np.clip(cap_gap, 0.0, None)) * self._d
        depth = np.minimum(radial, angular)

        y_edge = _SEL_YELLOW
        b_edge = _SEL_YELLOW + _SEL_BLACK
        w_yellow = np.clip(y_edge - depth + 0.5, 0.0, 1.0)
        w_black = np.clip(depth - y_edge + 0.5, 0.0, 1.0) * np.clip(b_edge - depth + 0.5, 0.0, 1.0)
        band = np.clip(w_yellow + w_black, 0.0, 1.0)
        frac_y = w_yellow / (w_yellow + w_black + 1e-6)

        cr, cg, cb = color
        R = (cr * frac_y).astype(np.uint8)
        G = (cg * frac_y).astype(np.uint8)
        B = (cb * frac_y).astype(np.uint8)
        A = np.clip(fill_cov * band * 255.0, 0, 255).astype(np.uint8)

        lin = self._lin
        rgba = self._sel_rgba
        rgba[lin, 0] = R
        rgba[lin, 1] = G
        rgba[lin, 2] = B
        rgba[lin, 3] = A
        return pygame.image.frombuffer(rgba.tobytes(), (self._size, self._size), "RGBA")
