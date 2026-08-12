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

"""The circle handle: a filled disc that punches through whatever bar or curve
it sits on, with an optional yellow selection halo.

Shared by every control that marks a value on a track — parametric/graphic EQ
band handles, the parameter-window handle, the mixer's fader/pan handles, and
the arc-ring value bubble — so they read as one visual language. Pure ``uilib``
(no panel deps) so any of them can import it without coupling to another's
module.
"""

from __future__ import annotations

from common.color import SELECT_COLOR
from uilib.glyphs.circle import CircleGlyph, RingGlyph
from uilib.glyphs.tint import tint_mask

HANDLE_R = 4
HALO_R = 6
HALO_COLOR = SELECT_COLOR

_ERASER_COLOR = (0, 0, 0)


def paint_circle_handle(
    ctx,
    cx: int,
    cy: int,
    color: tuple[int, int, int],
    selected: bool,
    *,
    radius: int = HANDLE_R,
    halo_radius: int = HALO_R,
    halo_half: float = 0.75,
) -> None:
    """Paint the handle (black eraser, coloured fill, optional halo).

    ``radius`` is the filled disc radius; the eraser is ``radius + 2`` so the
    1.5px annulus between them reads as a permanent black outline against the
    underlying track/curve. The yellow selection halo sits at ``halo_radius``
    with stroke half-width ``halo_half`` (1.5px visual at the default 0.75),
    just outside the eraser.
    """
    eraser = CircleGlyph(radius + 2)
    ctx.paste(tint_mask(eraser.render(), _ERASER_COLOR), (cx - eraser.radius, cy - eraser.radius))
    fill = CircleGlyph(radius)
    ctx.paste(tint_mask(fill.render(), color), (cx - fill.radius, cy - fill.radius))
    if selected:
        halo = RingGlyph(halo_radius, ring_half=halo_half)
        ctx.paste(tint_mask(halo.render(), HALO_COLOR), (cx - halo.half_size, cy - halo.half_size))