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

"""Band specifications for the TAP EQ/BW parametric EQ plugin (8 bands with bandwidth)."""

from __future__ import annotations

from plugins.eq.band_spec import BandSpec
from common.parameter import Symbol

_FREQ_RANGES: list[tuple[float, float]] = [
    (40.0, 280.0),
    (100.0, 500.0),
    (200.0, 1000.0),
    (400.0, 2800.0),
    (1000.0, 5000.0),
    (3000.0, 9000.0),
    (6000.0, 18000.0),
    (10000.0, 20000.0),
]

_COLORS: list[tuple[int, int, int]] = [
    (255, 110, 110),
    (255, 180, 80),
    (255, 230, 80),
    (130, 220, 110),
    (110, 200, 230),
    (140, 150, 240),
    (210, 130, 230),
    (240, 140, 180),
]

BAND_SPECS: tuple[BandSpec, ...] = tuple(
    BandSpec(
        name=f"B{i+1}",
        kind="peak",
        enable_sym=None,
        freq_sym=Symbol(f"Band{i+1}FreqHz"),
        q_sym=Symbol(f"Band{i+1}BandwidthOctaves"),
        gain_sym=Symbol(f"Band{i+1}GainDb"),
        shelf_side=None,
        freq_min=fmin,
        freq_max=fmax,
        q_min=0.1,
        q_max=5.0,
        gain_min=-50.0,
        gain_max=20.0,
        color=_COLORS[i],
        q_units="bw_oct",
    )
    for i, (fmin, fmax) in enumerate(_FREQ_RANGES)
)
