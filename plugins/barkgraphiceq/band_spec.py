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

"""Band specifications for the gx_barkgraphiceq plugin (24 bands, Bark scale)."""

from __future__ import annotations

from plugins.eq.band_spec import GraphicBandSpec
from plugins.eq.graphic import _graphic_palette
from common.parameter import Symbol

# Bark-scale center frequencies (approximate, from Bark scale literature).
# The TTL manifest declares only gain ports G1-G24 with no frequency metadata.
_BARK_FREQS: list[float] = [
    50, 150, 250, 350, 450, 570, 700, 840,
    1000, 1170, 1370, 1600, 1850, 2150, 2500, 2900,
    3400, 4000, 4800, 5800, 7000, 8500, 10500, 13500,
]

_colors = _graphic_palette(len(_BARK_FREQS))

BAND_SPECS: tuple[GraphicBandSpec, ...] = tuple(
    GraphicBandSpec(
        name=f"G{i+1}",
        freq_hz=freq,
        gain_sym=Symbol(f"G{i+1}"),
        gain_min=-30.0,
        gain_max=20.0,
        color=color,
    )
    for i, (freq, color) in enumerate(zip(_BARK_FREQS, _colors))
)
