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

"""Rounded-rectangle glyph with optional fill and per-side border.

A general-purpose building block for plugin tiles, pills, badges, and any
other widget that needs a filled rounded rect.

Everything is rendered into a single SRCALPHA surface using a numpy
signed-distance-field, so the fill, the border, and their corners all
share one analytic-AA pass. There is no compositing of separate fill
and border surfaces — the combined output is opaque wherever both the
fill and the border would cover, and AA-falloff only happens at the
outer edge of the border and the inner edge of the border. The border
corners land exactly on the straight edges so they connect seamlessly.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pygame

from uilib.paint import ColorLike

ColorRGB = tuple[int, int, int]


@dataclass(frozen=True)
class RectBorder:
    """Per-side border colors for a RoundedRectGlyph.

    Each side is optional. A ``None`` side is omitted from the rendered
    border (the fill still flows through that edge). Corner arcs take the
    color of the meeting horizontal edge — top for the top corners,
    bottom for the bottom corners — falling back to the vertical edge if
    the horizontal is unset.
    """

    top: ColorRGB | None = None
    right: ColorRGB | None = None
    bottom: ColorRGB | None = None
    left: ColorRGB | None = None


def _to_rgb(color: ColorLike | None) -> ColorRGB | None:
    """Normalize a color (name/tuple/pygame.Color) to an (r, g, b) tuple. None passes through."""
    if color is None:
        return None
    c = pygame.Color(color)
    return (c.r, c.g, c.b)


def _corner_color(
    h_color: ColorLike | None,
    v_color: ColorLike | None,
) -> ColorLike | None:
    """Pick the color for a corner: prefer the horizontal edge, fall back to vertical."""
    return h_color if h_color is not None else v_color


def _blit_rgb_alpha(surface: pygame.Surface, rgb_arr: np.ndarray, alpha_arr: np.ndarray) -> None:
    """Composite an (H, W, 3) RGB array and an (H, W) float alpha array onto a SRCALPHA surface.

    ``alpha_arr`` holds float values in [0.0, 1.0]; pygame's
    ``pixels_alpha`` is uint8, so the float must be scaled by 255 before
    the assignment — naive ``pa[:] = alpha_arr.T`` truncates every
    sub-1.0 alpha to 0 and the surface ends up fully transparent.
    """
    pixels = pygame.surfarray.pixels3d(surface)
    pixels[:, :, 0] = rgb_arr[:, :, 0].T
    pixels[:, :, 1] = rgb_arr[:, :, 1].T
    pixels[:, :, 2] = rgb_arr[:, :, 2].T
    del pixels
    pa = pygame.surfarray.pixels_alpha(surface)
    pa[:] = np.clip(alpha_arr.T * 255.0, 0, 255).astype(np.uint8)
    del pa


def _sdf_rounded_rect(width: int, height: int, radius: int) -> np.ndarray:
    """Signed distance from each pixel center to the nearest edge of a rounded rect.

    Negative inside, positive outside, with the magnitude equal to the
    distance in pixels. Pixel centers sit at (i + 0.5, j + 0.5) so a
    pixel exactly on the edge has SDF = 0.

    Uses the standard Inigo Quilez box-SDF construction:
      q = |p - center| - half_size + radius
      sdf = length(max(q, 0)) + min(max(q.x, q.y), 0) - radius
    which is the only formulation that's correct in all four regions
    (interior, edge band, corner band, outside). A naive per-edge
    ``max``-reduce gives wrong results because the corner-arc SDFs
    are positive and unbounded far from the corner, so they swamp the
    negative edge SDFs in the interior.
    """
    x = np.arange(width, dtype=float) + 0.5
    y = np.arange(height, dtype=float) + 0.5
    X, Y = np.meshgrid(x, y)
    cx = width / 2.0
    cy = height / 2.0
    r = float(radius)
    qx = np.abs(X - cx) - (width / 2.0) + r
    qy = np.abs(Y - cy) - (height / 2.0) + r
    outside = np.sqrt(np.maximum(qx, 0.0) ** 2 + np.maximum(qy, 0.0) ** 2)
    inside = np.minimum(np.maximum(qx, qy), 0.0)
    return outside + inside - r


@lru_cache(maxsize=256)
def _render_filled_rounded_rect(
    width: int,
    height: int,
    radius: int,
    fill: ColorLike | None,
    border_width: int,
    border_top: ColorLike | None,
    border_right: ColorLike | None,
    border_bottom: ColorLike | None,
    border_left: ColorLike | None,
) -> pygame.Surface:
    """Render fill + border as a single SRCALPHA surface with analytic AA.

    SDF conventions:
      - ``sdf > 0``         : outside the rounded rect
      - ``sdf < 0``         : inside the rounded rect
      - ``-bw <= sdf <= 0`` : on the border ring

    The fill is opaque for sdf < -border_width. The border is opaque on
    its ring. The alpha falls off linearly over 1 pixel at the outer
    edge of the border (sdf = 0) and the inner edge (sdf = -border_width).
    Per-side border colors are resolved at the corners via the
    ``_corner_color`` rule (horizontal edge wins, vertical falls back).
    """
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    has_border = any(c is not None for c in (border_top, border_right, border_bottom, border_left))
    has_fill = fill is not None
    if not has_fill and not has_border:
        return surf
    if border_width < 0:
        border_width = 0

    if radius < 0 or width < 2 * radius or height < 2 * radius:
        radius = 0

    if radius > 0:
        sdf = _sdf_rounded_rect(width, height, radius)
    else:
        # Square rect: same construction with radius=0 reduces to the
        # correct axis-aligned box SDF.
        x = np.arange(width, dtype=float) + 0.5
        y = np.arange(height, dtype=float) + 0.5
        X, Y = np.meshgrid(x, y)
        cx = width / 2.0
        cy = height / 2.0
        qx = np.abs(X - cx) - (width / 2.0)
        qy = np.abs(Y - cy) - (height / 2.0)
        outside = np.sqrt(np.maximum(qx, 0.0) ** 2 + np.maximum(qy, 0.0) ** 2)
        inside = np.minimum(np.maximum(qx, qy), 0.0)
        sdf = outside + inside

    bw = float(border_width) if has_border else 0.0

    # Build an RGB array: pick the right color for every pixel.
    H, W = sdf.shape
    rgb = np.zeros((H, W, 3), dtype=np.uint8)
    alpha = np.zeros((H, W), dtype=np.float32)

    if has_fill:
        # Normalize the fill so we can broadcast it to the rgb array
        # (pygame accepts color names, but numpy needs an int tuple).
        fill_rgb = _to_rgb(fill)
        # Fill is opaque for sdf < -bw - 0.5, transparent for sdf > 0.5.
        # Inside the border ring, the border overrides the fill color.
        fill_mask = sdf < bw + 0.5 if has_border else sdf < 0.5
        if fill_mask.any():
            rgb[fill_mask] = fill_rgb
            fill_alpha = np.clip(0.5 - sdf, 0.0, 1.0)
            alpha[fill_mask] = np.maximum(alpha[fill_mask], fill_alpha[fill_mask])

    if has_border and bw > 0.0:
        # Pick the border color for each pixel by where it sits in the
        # rounded rect. Top region → border_top, bottom → border_bottom,
        # middle band → left/right. Corners use _corner_color (horizontal
        # edge wins, vertical falls back). This avoids needing per-side
        # 2D SDFs and matches the docstring's contract.
        x = np.arange(width, dtype=float) + 0.5
        y = np.arange(height, dtype=float) + 0.5
        Ycol = y[:, None]
        Xrow = x[None, :]

        # Ring mask: pixels inside the rect AND within `bw` of the edge.
        on_ring = (sdf >= -bw - 0.5) & (sdf <= 0.5)
        if on_ring.any():
            # AA coverage: 1.0 for -bw+0.5 < sdf < -0.5, linear falloff at both edges.
            ring_alpha = np.clip(0.5 - sdf, 0.0, 1.0) * np.clip(sdf + bw + 0.5, 0.0, 1.0)

            # The edge bands are `max(radius, bw)` wide so the ring (which
            # is `bw` pixels deep) is fully captured even when radius=0
            # (square rect: no corner zone, straight edges cover the full
            # ring). The corner zone within each band is `radius` wide —
            # empty for radius=0, so corners get no pixels and the edge
            # stamps cover the entire band.
            band = max(float(radius), bw)
            top_mask = (Ycol <= band) & on_ring
            bot_mask = (Ycol >= float(height) - band) & on_ring
            mid_mask = on_ring & ~top_mask & ~bot_mask

            def _stamp(mask: np.ndarray, color: ColorLike) -> None:
                if not mask.any():
                    return
                rgb[mask] = _to_rgb(color)

            # Top corners + top edge.
            _stamp(top_mask & (Xrow <= float(radius)),
                   _corner_color(border_top, border_left))
            _stamp(top_mask & (Xrow >= float(width) - float(radius)),
                   _corner_color(border_top, border_right))
            _stamp(top_mask & (Xrow > float(radius)) & (Xrow < float(width) - float(radius)),
                   border_top)

            # Bottom corners + bottom edge.
            _stamp(bot_mask & (Xrow <= float(radius)),
                   _corner_color(border_bottom, border_left))
            _stamp(bot_mask & (Xrow >= float(width) - float(radius)),
                   _corner_color(border_bottom, border_right))
            _stamp(bot_mask & (Xrow > float(radius)) & (Xrow < float(width) - float(radius)),
                   border_bottom)

            # Middle band: left/right edges.
            _stamp(mid_mask & (Xrow <= band), border_left)
            _stamp(mid_mask & (Xrow >= float(width) - band), border_right)

            # Composite border alpha over fill: take the max so the ring is
            # fully opaque over the body (no gap at the inner edge where
            # ring_alpha→0 but fill_alpha=1), and AA falloff is preserved
            # at the outer edge. Applied once after all color stamps.
            np.maximum(alpha, ring_alpha, out=alpha)

    # Also clip the fill to the rounded-rect boundary: pixels outside the
    # rect (sdf > 0) must be fully transparent even if the fill was written.
    outside = sdf > 0.5
    if outside.any():
        alpha[outside] = 0.0
        rgb[outside] = 0

    _blit_rgb_alpha(surf, rgb, alpha)
    return surf


class RoundedRectGlyph:
    """Filled rounded rectangle with optional per-side border.

    Results are cached by the full parameter set so multiple glyph
    instances with the same shape share the same underlying surface.
    Fill and border are rendered into a single surface, not composited.
    """

    def __init__(
        self,
        width: int,
        height: int,
        radius: int,
        fill: ColorRGB | None = None,
        border: RectBorder | None = None,
        border_width: int = 1,
    ) -> None:
        self._w = int(width)
        self._h = int(height)
        self._r = int(radius)
        self._fill = fill
        self._border = border or RectBorder()
        self._border_width = int(border_width)

    @property
    def width(self) -> int:
        return self._w

    @property
    def height(self) -> int:
        return self._h

    def render(self) -> pygame.Surface:
        """Render fill + border as a single opaque SRCALPHA surface."""
        return _render_filled_rounded_rect(
            self._w,
            self._h,
            self._r,
            self._fill,
            self._border_width,
            self._border.top,
            self._border.right,
            self._border.bottom,
            self._border.left,
        )
