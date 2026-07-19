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

"""Procedural toolbar-tile glyphs for the Audio & MIDI menu.

Three states of the toolbar tile that opens the Audio & MIDI menu. A
4-bar EQ silhouette (each bar 2px wide with a 2px gap; bar heights
6/14/16/8 px from left so the nominal glyph reads as the familiar EQ
icon) and the muted/rolling states are its visible mutations:

- ``nominal`` — blue EQ bars (idle, transport stopped).
- ``muted``   — red bars with a diagonal slash — the universal mute glyph.
- ``rolling`` — blue bars with a play-triangle overlay — transport is rolling.

The play-triangle is analytically anti-aliased with a 1.5px black outline,
mirroring ``paint_circle_handle``'s eraser/fill construction (dilated black
mask pasted first, coloured mask pasted on top — the exposed rim reads as
the outline). Other primitives use the jaggie pixel look to stay close to
the original ``eq_blue.png`` silhouette.

Rendered at 16×16 with ``pygame.SRCALPHA`` and cached per state. The LCD's
``update_audio_midi_tile()`` swaps these into ``w_eq`` based on the handler's
``jack_mute`` / ``transport_rolling`` state. ``draw_tools()`` seeds the tile
with the nominal glyph so the procedural pipeline owns the surface from t=0.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Literal

import numpy as np
import pygame

State = Literal["nominal", "muted", "rolling"]

_SIZE = 16
# Same blue as the toolbar image; same red as a footswitch-toggled mute.
_NOMINAL_COLOR = (90, 160, 230)
_MUTED_COLOR = (210, 60, 40)
_TRIANGLE_FILL_WHITE = (235, 235, 235)
_ERASER_COLOR = (0, 0, 0)

# Bar geometry — four equal-width columns, each 2px wide with 2px gap, centred
# horizontally. Bar heights (top-down) trace the familiar EQ-bar silhouette so the
# nominal glyph remains visually identical to the shipped PNG.
_BAR_W = 2
_BAR_GAP = 2
_BAR_HEIGHTS = (6, 14, 16, 8)
_BAR_BASELINE = 16

# Play-triangle in the upper-right corner — conventional "transport rolling" mark.
# Sized so the 1.5px black outline still leaves a clearly-triangular fill — a
# smaller triangle collapses to a "flag" once the eraser dilation eats both edges.
_PLAY_VERTICES: tuple[tuple[float, float], tuple[float, float], tuple[float, float]] = (
    (8.5, 0.5),
    (15.5, 6.0),
    (8.5, 11.5),
)
_PLAY_OUTLINE_PX = 1.5  # black eraser dilation, matching circle handle's outline band


def _bar_x(i: int) -> int:
    # Centre the 4-bar block (4*2 + 3*2 = 14 px) within the 16-wide glyph.
    return 1 + i * (_BAR_W + _BAR_GAP)


def _draw_bars(surf: pygame.Surface, color: tuple[int, int, int]) -> None:
    for i, h in enumerate(_BAR_HEIGHTS):
        x = _bar_x(i)
        y = _BAR_BASELINE - h
        surf.fill(color, rect=pygame.Rect(x, y, _BAR_W, h))


def _draw_slash(surf: pygame.Surface, color: tuple[int, int, int]) -> None:
    # Diagonal slash corner-to-corner, 2px thick (drawn as two offset lines).
    for off in range(2):
        pygame.draw.line(surf, color, (1 + off, 1), (_SIZE - 2, _SIZE - 2 - off), width=1)
        pygame.draw.line(surf, color, (1, 1 + off), (_SIZE - 2 - off, _SIZE - 2), width=1)


# ── analytic anti-aliased polygon mask ───────────────────────────────────────
#
# Coverage for a pixel = clip(signed_dist + 0.5, 0, 1), where signed_dist is the
# pixel centre's minimum signed perpendicular distance to any polygon edge (positive
# inside). `dilate` shifts the boundary outward by N px so a dilated pasting of
# the black eraser produces a rim around the un-dilated fill — same eraser/fill
# construction the circle handle uses.


@lru_cache(maxsize=8)
def _polygon_masks(
    vertices: tuple[tuple[float, float], ...],
) -> tuple[np.ndarray, np.ndarray, int, int]:
    """Cached analytic coverage + dilation band for ``vertices``.

    Returns ``(coverage, ring_band, paste_x, paste_y)`` where:

    - ``coverage`` is the pixel-wise anti-aliased coverage of the un-dilated
      polygon ([0.0, 1.0], shape (h, w)).
    - ``ring_band`` is the coverage of the 1.5px outline band —
      ``clip(dilated_coverage - coverage, 0, 1)`` — what would be visible as
      the black rim around the filled triangle.
    - ``paste_x, paste_y`` is the blit offset.

    Separate masks (rather than two dilations pasted in sequence) avoid the
    eraser punching through the bars underneath; the band is composited on
    top of the EQ bars and only where the rim should show.
    """
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    pad = int(math.ceil(_PLAY_OUTLINE_PX)) + 1
    paste_x = int(math.floor(min(xs))) - pad
    paste_y = int(math.floor(min(ys))) - pad
    maxx = int(math.ceil(max(xs))) + pad
    maxy = int(math.ceil(max(ys))) + pad
    w = maxx - paste_x + 1
    h = maxy - paste_y + 1

    V = np.array(vertices, dtype=np.float64) - np.array([paste_x, paste_y])
    grid_x, grid_y = np.meshgrid(np.arange(w), np.arange(h))
    p = np.stack([grid_x, grid_y], axis=-1).astype(np.float64)  # (h, w, 2)

    signed = np.full((h, w), np.inf, dtype=np.float64)
    n = len(V)
    for i in range(n):
        a = V[i]
        b = V[(i + 1) % n]
        d = b - a
        normal = np.array([-d[1], d[0]], dtype=np.float64)
        norm_len = math.hypot(float(normal[0]), float(normal[1]))
        if norm_len == 0:
            continue
        normal = normal / norm_len
        c = V[(i + 2) % n] - a
        if float(np.dot(c, normal)) < 0:
            normal = -normal
        signed_dist = (p - a) @ normal  # (h, w)
        signed = np.minimum(signed, signed_dist)

    cov_inner = np.clip(signed + 0.5, 0.0, 1.0)
    cov_outer = np.clip((signed + _PLAY_OUTLINE_PX) + 0.5, 0.0, 1.0)
    band = np.clip(cov_outer - cov_inner, 0.0, 1.0)
    return cov_inner, band, paste_x, paste_y


def _draw_play_triangle(surf: pygame.Surface, color: tuple[int, int, int]) -> None:
    # white fill covers bars inside the triangle
    # black outline lands in the 1.5px rim around the fill
    cov_inner, band, ox, oy = _polygon_masks(_PLAY_VERTICES)

    def _paste(cov: np.ndarray, rgb: tuple[int, int, int]) -> None:
        alpha = (cov * 255).astype(np.uint8)
        # ``tint_mask`` keys on surface identity — build a fresh surface per
        # band so the alpha array matches the size we're pasting into.
        h, w = alpha.shape
        tmp = pygame.Surface((w, h), pygame.SRCALPHA)
        pixels = pygame.surfarray.pixels3d(tmp)
        pixels[:] = rgb
        del pixels
        pa = pygame.surfarray.pixels_alpha(tmp)
        pa[:] = alpha.T
        del pa
        surf.blit(tmp, (ox, oy))

    _paste(cov_inner, color)  # white fill over bars
    _paste(band, _ERASER_COLOR)  # 1.5px black rim over fill's edge


@lru_cache(maxsize=4)
def _render(state: State) -> pygame.Surface:
    surf = pygame.Surface((_SIZE, _SIZE), pygame.SRCALPHA)
    if state == "muted":
        _draw_bars(surf, _MUTED_COLOR)
        _draw_slash(surf, _TRIANGLE_FILL_WHITE)
    elif state == "rolling":
        _draw_bars(surf, _NOMINAL_COLOR)
        _draw_play_triangle(surf, _TRIANGLE_FILL_WHITE)
    else:
        _draw_bars(surf, _NOMINAL_COLOR)
    return surf


def audio_midi_tile_glyph(state: State) -> pygame.Surface:
    """Return the cached 16×16 ``SRCALPHA`` Surface for ``state``."""
    return _render(state).copy()
