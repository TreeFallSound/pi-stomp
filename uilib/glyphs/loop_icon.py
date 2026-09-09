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

"""Loop-track icon: a horizontal pill/racetrack outline with two staggered arrowheads.

The top arrowhead (→) sits right-of-centre and the bottom (←) sits left-of-centre,
suggesting two runners chasing each other clockwise around the oval.

Rendering pipeline: PIL 4× supersampling + LANCZOS downscale for analytic-quality
AA at small sizes.  Returns a white SRCALPHA pygame surface (alpha = coverage);
callers tint it with tint_mask().
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pygame
from PIL import Image, ImageDraw


@lru_cache(maxsize=8)
def _render(width: int, height: int) -> pygame.Surface:
    s = 8  # supersampling factor
    W, H = width * s, height * s

    # Stroke width ≈ 2/14 of final height, rounded to even at scale.
    sw = max(s * 2, round(height * s / 7) // 2 * 2)

    # Inset so the outer stroke edge doesn't clip at the canvas boundary.
    pad = sw // 2 + s

    big = Image.new("L", (W, H), 0)
    bd = ImageDraw.Draw(big)

    # Stadium (pill) outline — full-semicircle caps.
    inner_h = H - 2 * pad
    bd.rounded_rectangle(
        (pad, pad, W - pad, H - pad),
        radius=inner_h // 2,
        outline=255,
        width=sw,
    )

    mid_x  = W // 2
    top_y  = pad + sw // 2          # centreline of top stroke
    bot_y  = H - pad - sw // 2      # centreline of bottom stroke
    al     = (sw * 3) // 4          # arrow half-length (base → tip)
    ab     = round(sw * 1.5)            # arrow half-base — wider than track for visibility
    gap    = s * 3                   # gap between arrowhead tip and resuming track
    offset = W // 8                  # stagger: top arrow right, bottom arrow left

    top_cx = mid_x + offset
    bot_cx = mid_x - offset

    # Top → : base at (top_cx - al), tip at (top_cx + al).
    # Erase from the base rightward; base side stays flush with incoming track.
    bd.rectangle((top_cx - al, 0, top_cx + al + gap, pad + sw + s), fill=0)
    bd.polygon(
        [(top_cx - al, top_y - ab), (top_cx - al, top_y + ab), (top_cx + al, top_y)],
        fill=255,
    )

    # Bottom ← : base at (bot_cx + al), tip at (bot_cx - al).
    # Erase from the base leftward; base side stays flush with incoming track.
    bd.rectangle((bot_cx - al - gap, H - pad - sw - s, bot_cx + al, H), fill=0)
    bd.polygon(
        [(bot_cx + al, bot_y - ab), (bot_cx + al, bot_y + ab), (bot_cx - al, bot_y)],
        fill=255,
    )

    # Downscale to target size with LANCZOS for sub-pixel sharpness.
    mask = big.resize((width, height), Image.Resampling.LANCZOS)

    # White SRCALPHA surface — tint_mask() handles colourisation at blit time.
    mask_arr = np.frombuffer(mask.tobytes(), dtype=np.uint8).reshape((height, width)).T
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    pix = pygame.surfarray.pixels3d(surf)
    alp = pygame.surfarray.pixels_alpha(surf)
    pix[:, :, :] = 255
    alp[:, :] = mask_arr
    del pix, alp
    return surf


class LoopIconGlyph:
    """Racetrack loop icon: a wider-than-tall pill outline with two chase arrows.

    Renders as a white alpha mask; use tint_mask() to colourise before blitting.
    Geometry is cached at module level on (width, height) — multiple widget
    instances sharing the same size pay only one render.
    """

    def __init__(self, width: int = 42, height: int = 14) -> None:
        self._width = width
        self._height = height

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def render(self) -> pygame.Surface:
        return _render(self._width, self._height)
