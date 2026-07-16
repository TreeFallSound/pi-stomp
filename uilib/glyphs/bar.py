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

"""Orientation-aware track+fill bar — the graphic-EQ column primitive, shared
so list-style rows can render the same visual language horizontally."""

from __future__ import annotations

from typing import Literal

from uilib.box import Box

# Shared bar palette. Lives here (pure uilib) so plugin panels pull it without a
# plugins→plugins import.
TRACK_COLOR = (40, 40, 40)
FILL_INACTIVE = (160, 160, 160)
FILL_ACTIVE = (240, 240, 240)
READOUT_COLOR = (200, 200, 200)

Orientation = Literal["vertical", "horizontal"]


def paint_bar(
    ctx,
    *,
    box: Box,
    orientation: Orientation,
    frac: float,
    track_color: tuple[int, int, int],
    fill_color: tuple[int, int, int],
    thickness: int,
) -> tuple[int, int]:
    """Draw a track + fill bar centred in the cross-axis of *box* at *thickness*
    px. Vertical fill grows bottom→top, horizontal grows left→right. *frac* is
    clamped to 0..1. Returns the value-end centre point for a node/marker."""
    frac = max(0.0, min(1.0, frac))
    if orientation == "vertical":
        cx = (box.x0 + box.x1) // 2
        bar_x = cx - thickness // 2
        ctx.draw_rectangle(Box(bar_x, box.y0, bar_x + thickness, box.y1), fill=track_color)
        end = int(box.y1 - frac * (box.y1 - box.y0))
        if end < box.y1:
            ctx.draw_rectangle(Box(bar_x, end, bar_x + thickness, box.y1), fill=fill_color)
        return cx, end
    cy = (box.y0 + box.y1) // 2
    bar_y = cy - thickness // 2
    ctx.draw_rectangle(Box(box.x0, bar_y, box.x1, bar_y + thickness), fill=track_color)
    end = int(box.x0 + frac * (box.x1 - box.x0))
    if end > box.x0:
        ctx.draw_rectangle(Box(box.x0, bar_y, end, bar_y + thickness), fill=fill_color)
    return end, cy
