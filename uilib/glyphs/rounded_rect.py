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

import numpy as np
import pygame

from common.color import ColorRGB, RectBorder
from uilib.paint import ColorLike


_GLYPH_CACHE: dict[tuple, pygame.Surface] = {}


def _hashable(c: ColorLike | None) -> object:
    """Coerce a ColorLike into a hashable cache key.

    ColorLike includes Sequence[int] (unhashable), pygame.Color (which is
    actually hashable but uses identity), and plain strings. We normalise
    to a tuple so the cache key is purely value-based.
    """
    if c is None:
        return None
    if isinstance(c, (tuple, frozenset)):
        return tuple(c)
    if isinstance(c, pygame.Color):
        return (c.r, c.g, c.b, c.a)
    return c


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

    fill_rgb = _to_rgb(fill) if has_fill else (0, 0, 0)
    if has_fill:
        assert fill_rgb is not None
        # Fill is opaque for sdf < -bw - 0.5, transparent for sdf > 0.5.
        # Inside the border ring, the border overrides the fill color.
        fill_mask = sdf < bw + 0.5 if has_border else sdf < 0.5
        if fill_mask.any():
            rgb[fill_mask] = fill_rgb
            fill_alpha = np.clip(0.5 - sdf, 0.0, 1.0)
            alpha[fill_mask] = np.maximum(alpha[fill_mask], fill_alpha[fill_mask])

    if has_border and bw > 0.0:
        # Per-pixel border color with smooth band transitions and inner-edge AA.
        #
        # The border color at each ring pixel is a blend of the horizontal
        # edge color (top or bottom) and the vertical edge color (left or
        # right). The horizontal/vertical blend uses a 1-pixel linear
        # transition at the band boundaries, so the top edge flows into
        # the left edge over one pixel instead of a hard color cut.
        #
        # At the inner edge of the ring (sdf ≈ -bw), the border color
        # blends with the fill color (or fades to transparent when there
        # is no fill), giving smooth AA against the body instead of a
        # hard staircase.
        #
        # Per the RectBorder contract: horizontal edges win at corners,
        # vertical edges fall back when the horizontal is None. A None
        # side means no border on that edge — the fill flows through.
        x = np.arange(width, dtype=float) + 0.5
        y = np.arange(height, dtype=float) + 0.5
        Ycol = y[:, None]  # (H, 1)
        Xrow = x[None, :]  # (1, W)

        on_ring = (sdf >= -bw - 0.5) & (sdf <= 0.5)
        if on_ring.any():
            band = max(float(radius), bw)

            # Band weights with 1-pixel linear transition at the boundaries.
            # top_w: 1.0 in the top band → 0.0 in the middle, transition at y=band.
            # bot_w: 1.0 in the bottom band → 0.0 in the middle.
            top_w = np.clip(band + 0.5 - Ycol, 0.0, 1.0)
            bot_w = np.clip(Ycol - (float(height) - band - 0.5), 0.0, 1.0)
            # Zero out where the color is None (that edge has no border).
            if border_top is None:
                top_w = np.zeros_like(top_w)
            if border_bottom is None:
                bot_w = np.zeros_like(bot_w)
            h_weight = top_w + bot_w  # (H, 1)

            # Top vs bottom fraction for horizontal color.
            top_frac = top_w / (h_weight + 1e-10)  # (H, 1): 1.0 top, 0.0 bottom

            # Vertical edge validity: 1.0 on the left/right edge, 0.0 elsewhere.
            # This prevents the vertical color from leaking to the top-center
            # when the top color is None (fill flows through that edge).
            v_valid = np.zeros((height, width), dtype=np.float32)
            if border_left is not None:
                v_valid += np.clip(band + 0.5 - Xrow, 0.0, 1.0)
            if border_right is not None:
                v_valid += np.clip(Xrow - (float(width) - band - 0.5), 0.0, 1.0)
            v_valid = np.clip(v_valid, 0.0, 1.0)  # (H, W)

            # Left vs right fraction for vertical color.
            # Hard split at width/2 — the ring doesn't span the center, so
            # the left and right edges never meet.
            if border_left is not None and border_right is not None:
                left_frac = np.where(Xrow < float(width) / 2.0, 1.0, 0.0)
            elif border_left is not None:
                left_frac = np.ones_like(Xrow)
            else:
                left_frac = np.zeros_like(Xrow)

            # Resolve colors to float arrays (None → (0,0,0), but v_valid/h_weight
            # will be 0 there so the color never contributes).
            top_c = np.array(_to_rgb(border_top) or (0, 0, 0), dtype=np.float32)
            bot_c = np.array(_to_rgb(border_bottom) or (0, 0, 0), dtype=np.float32)
            left_c = np.array(_to_rgb(border_left) or (0, 0, 0), dtype=np.float32)
            right_c = np.array(_to_rgb(border_right) or (0, 0, 0), dtype=np.float32)

            # Per-pixel border color: (H, W, 3)
            # h_color: top or bottom, depending on which band. (H, 1, 3)
            # v_color: left or right, depending on X position. (1, W, 3)
            h_color = top_c[None, None, :] * top_frac[:, :, None] + bot_c[None, None, :] * (1.0 - top_frac[:, :, None])
            v_color = left_c[None, None, :] * left_frac[:, :, None] + right_c[None, None, :] * (
                1.0 - left_frac[:, :, None]
            )

            # Border weight: horizontal takes priority (corner rule), vertical fills in.
            # At a top-left corner: h_weight=1, v_valid=1 → border_weight=1, h_frac=1 → top color.
            # At a mid-left edge: h_weight=0, v_valid=1 → border_weight=1, h_frac=0 → left color.
            # At a band boundary on the left edge: h_weight=0.5, v_valid=1 → h_frac=0.5 → 50/50 blend.
            # At top-center with top=None: h_weight=0, v_valid=0 → border_weight=0 → no border (fill flows).
            border_weight = h_weight + v_valid * (1.0 - h_weight)  # (H, W)
            h_frac = h_weight / (border_weight + 1e-10)  # (H, W)
            border_color = h_color * h_frac[:, :, None] + v_color * (1.0 - h_frac[:, :, None])

            # Inner-edge AA: 1.0 at the outer side of the ring, 0.0 at the inner side.
            # Blends the border color with the fill (or fades to transparent).
            inner_aa = np.clip(sdf + bw + 0.5, 0.0, 1.0)  # (H, W)

            if has_fill:
                # Blend border with fill: at the inner edge, the border color
                # smoothly transitions to the fill color. Alpha stays as
                # fill_alpha (already set, fully opaque inside the rect).
                fill_rgb_arr = np.array(fill_rgb, dtype=np.float32)
                coverage = border_weight * inner_aa  # (H, W)
                blended = border_color * coverage[:, :, None] + fill_rgb_arr * (1.0 - coverage[:, :, None])
                rgb[on_ring] = blended[on_ring].astype(np.uint8)
            else:
                # No fill: ring alpha = border_weight * inner_aa * outer_aa.
                # Both edges of the ring have AA falloff.
                outer_aa = np.clip(0.5 - sdf, 0.0, 1.0)
                ring_alpha = border_weight * inner_aa * outer_aa
                rgb[on_ring] = border_color[on_ring].astype(np.uint8)
                alpha = np.maximum(alpha, ring_alpha)

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
        fill: ColorLike | None = None,
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
        """Render fill + border as a single opaque SRCALPHA surface.

        Cached by (w, h, r, fill, bw, top, right, bottom, left) so glyphs
        that share a shape (and color) share the same surface. The cache
        lives outside the renderer because pygame.Color's __hash__ isn't
        typed in the pygame stubs, so lru_cache can't be applied to a
        function taking ColorLike directly.
        """
        key = (
            self._w,
            self._h,
            self._r,
            _hashable(self._fill),
            self._border_width,
            _hashable(self._border.top),
            _hashable(self._border.right),
            _hashable(self._border.bottom),
            _hashable(self._border.left),
        )
        cached = _GLYPH_CACHE.get(key)
        if cached is not None:
            return cached
        surf = _render_filled_rounded_rect(
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
        if len(_GLYPH_CACHE) >= 256:
            _GLYPH_CACHE.pop(next(iter(_GLYPH_CACHE)))
        _GLYPH_CACHE[key] = surf
        return surf
