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

"""Tape-reel spinner glyph with analytic anti-aliasing.

A filled disk body with a ring rim, hub dot at center, and N evenly-spaced
spokes that rotate. Renders to an SRCALPHA surface with colors applied
directly. Disk/rim/hub coverage maps are precomputed; spoke coverage is
precomputed for all rotation steps on first render() call.

Blit render() at (cx - half_size, cy - half_size) to centre on (cx, cy).
"""

from __future__ import annotations

import math

import numpy as np
import pygame

ColorRGB = tuple[int, int, int]

_N_FRAMES = 36  # precomputed rotation steps (10° each)


def _segment_coverage(
    X: np.ndarray,
    Y: np.ndarray,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    half_width: float,
) -> np.ndarray:
    """Anti-aliased coverage of a line segment with butt caps."""
    dx = x1 - x0
    dy = y1 - y0
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        d_perp = np.sqrt((X - x0) ** 2 + (Y - y0) ** 2)
        return np.clip(half_width + 0.5 - d_perp, 0.0, 1.0)
    t_unclamped = ((X - x0) * dx + (Y - y0) * dy) / L2
    perp = np.abs((X - x0) * dy - (Y - y0) * dx) / np.sqrt(L2)
    cov_perp = np.clip(half_width + 0.5 - perp, 0.0, 1.0)
    L = np.sqrt(L2)
    t = np.clip(t_unclamped, 0.0, 1.0)
    along = np.abs(t - t_unclamped) * L
    cov_along = np.clip(half_width + 0.5 - along, 0.0, 1.0)
    return cov_perp * cov_along


class SpinnerGlyph:
    """Tape-reel spinner: filled disk with rim, hub dot, and rotating spokes.

    Precomputes body/rim/hub coverage in __init__; only spoke coverage
    (4 per frame) is computed in render().

    Blit render() at (cx - half_size, cy - half_size) to centre on (cx, cy).
    """

    def __init__(
        self,
        outer_r: int,
        hub_r: int,
        n_spokes: int = 4,
        spoke_half: float = 0.9,
    ) -> None:
        self._outer_r = int(outer_r)
        self._hub_r = int(hub_r)
        self._n_spokes = n_spokes
        self._spoke_half = spoke_half

        margin = 2  # rim AA margin
        self._half = self._outer_r + margin
        self._size = 2 * self._half + 1

        xs = np.arange(self._size, dtype=float)
        ys = np.arange(self._size, dtype=float)
        X, Y = np.meshgrid(xs, ys)
        self._X = X
        self._Y = Y

        dx = X - self._half
        dy = Y - self._half
        d = np.sqrt(dx**2 + dy**2)

        rim_half = 1.0
        self._body_cov: np.ndarray = np.clip(self._outer_r + 0.5 - d, 0.0, 1.0)
        self._rim_cov: np.ndarray = np.clip(rim_half + 0.5 - np.abs(d - self._outer_r), 0.0, 1.0)
        self._hub_cov: np.ndarray = np.clip(self._hub_r + 0.5 - d, 0.0, 1.0)

        # Precompute spoke coverage for all rotation steps (avoids per-frame numpy work).
        self._spoke_covs: list[np.ndarray] = []
        angle_step = 360.0 / self._n_spokes
        for frame in range(_N_FRAMES):
            rot = frame * 360.0 / _N_FRAMES
            cov = np.zeros((self._size, self._size), dtype=float)
            for i in range(self._n_spokes):
                rad = math.radians(rot + i * angle_step)
                sx = math.sin(rad)
                sy = -math.cos(rad)
                x0 = self._half + sx * (self._hub_r + 1)
                y0 = self._half + sy * (self._hub_r + 1)
                x1 = self._half + sx * (self._outer_r - 2)
                y1 = self._half + sy * (self._outer_r - 2)
                cov = np.maximum(cov, _segment_coverage(X, Y, x0, y0, x1, y1, self._spoke_half))
            self._spoke_covs.append(cov * self._body_cov)

        # Per-color-set frame cache: populated lazily on first render() call.
        self._frame_cache: dict[tuple[ColorRGB, ColorRGB, ColorRGB, ColorRGB], list[pygame.Surface]] = {}

    @property
    def half_size(self) -> int:
        return self._half

    @property
    def size(self) -> int:
        return self._size

    def render(
        self,
        rotation_deg: float,
        body_color: ColorRGB,
        rim_color: ColorRGB,
        hub_color: ColorRGB,
        spoke_color: ColorRGB,
    ) -> pygame.Surface:
        """Return SRCALPHA surface with the spinner drawn at rotation_deg."""
        color_key = (body_color, rim_color, hub_color, spoke_color)
        frames = self._frame_cache.get(color_key)
        if frames is None:
            frames = self._bake_frames(body_color, rim_color, hub_color, spoke_color)
            self._frame_cache[color_key] = frames
        frame_idx = int(round(rotation_deg * _N_FRAMES / 360.0)) % _N_FRAMES
        return frames[frame_idx]

    def _bake_frames(
        self,
        body_color: ColorRGB,
        rim_color: ColorRGB,
        hub_color: ColorRGB,
        spoke_color: ColorRGB,
    ) -> list[pygame.Surface]:
        body_cov = self._body_cov
        rim_cov = self._rim_cov
        hub_cov = self._hub_cov
        br, bg, bb = body_color
        rr, rg, rb = rim_color
        hr, hg, hb = hub_color
        sr, sg, sb = spoke_color

        # Static layers (body + rim + hub) — same across all frames.
        A = np.clip(np.maximum(body_cov, rim_cov) * 255, 0, 255).astype(np.uint8)
        base_R = body_cov * br
        base_G = body_cov * bg
        base_B = body_cov * bb
        base_R = base_R * (1.0 - rim_cov) + rim_cov * rr
        base_G = base_G * (1.0 - rim_cov) + rim_cov * rg
        base_B = base_B * (1.0 - rim_cov) + rim_cov * rb
        base_R = base_R * (1.0 - hub_cov) + hub_cov * hr
        base_G = base_G * (1.0 - hub_cov) + hub_cov * hg
        base_B = base_B * (1.0 - hub_cov) + hub_cov * hb

        surfs: list[pygame.Surface] = []
        for spoke_cov in self._spoke_covs:
            R = base_R * (1.0 - spoke_cov) + spoke_cov * sr
            G = base_G * (1.0 - spoke_cov) + spoke_cov * sg
            B = base_B * (1.0 - spoke_cov) + spoke_cov * sb
            surf = pygame.Surface((self._size, self._size), pygame.SRCALPHA)
            pix = pygame.surfarray.pixels3d(surf)
            pix[:, :, 0] = np.clip(R, 0, 255).astype(np.uint8).T
            pix[:, :, 1] = np.clip(G, 0, 255).astype(np.uint8).T
            pix[:, :, 2] = np.clip(B, 0, 255).astype(np.uint8).T
            del pix
            pa = pygame.surfarray.pixels_alpha(surf)
            pa[:] = A.T
            del pa
            surfs.append(surf)
        return surfs
