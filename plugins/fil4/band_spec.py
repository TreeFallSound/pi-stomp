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

"""Band specifications for the fil4 / x42-eq parametric EQ plugin."""

from __future__ import annotations

from plugins.eq.band_spec import BandSpec
from common.parameter import Symbol

BAND_SPECS: tuple[BandSpec, ...] = (
    BandSpec("HP", "hp", Symbol("HighPass"), Symbol("HPfreq"), Symbol("HPQ"), None, None,
             20.0, 1250.0, 0.0, 1.4, color=(255, 110, 110), q_units="q"),
    BandSpec("LS", "shelf", Symbol("LSsec"), Symbol("LSfreq"), Symbol("LSq"), Symbol("LSgain"), "low",
             25.0, 400.0, 0.0625, 4.0, color=(255, 180, 80), q_units="x42_shelf_slope"),
    BandSpec("B1", "peak", Symbol("sec1"), Symbol("freq1"), Symbol("q1"), Symbol("gain1"), None,
             20.0, 2000.0, 0.0625, 4.0, color=(255, 230, 80),
             filter_topology="regalia_mitra", q_units="bw_oct"),
    BandSpec("B2", "peak", Symbol("sec2"), Symbol("freq2"), Symbol("q2"), Symbol("gain2"), None,
             40.0, 4000.0, 0.0625, 4.0, color=(130, 220, 110),
             filter_topology="regalia_mitra", q_units="bw_oct"),
    BandSpec("B3", "peak", Symbol("sec3"), Symbol("freq3"), Symbol("q3"), Symbol("gain3"), None,
             100.0, 10000.0, 0.0625, 4.0, color=(110, 200, 230),
             filter_topology="regalia_mitra", q_units="bw_oct"),
    BandSpec("B4", "peak", Symbol("sec4"), Symbol("freq4"), Symbol("q4"), Symbol("gain4"), None,
             200.0, 20000.0, 0.0625, 4.0, color=(140, 150, 240),
             filter_topology="regalia_mitra", q_units="bw_oct"),
    BandSpec("HS", "shelf", Symbol("HSsec"), Symbol("HSfreq"), Symbol("HSq"), Symbol("HSgain"), "high",
             1000.0, 16000.0, 0.0625, 4.0, color=(210, 130, 230), q_units="x42_shelf_slope"),
    BandSpec("LP", "lp", Symbol("LowPass"), Symbol("LPfreq"), Symbol("LPQ"), None, None,
             500.0, 20000.0, 0.0, 1.4, color=(240, 140, 180), q_units="q"),
)

PLUGIN_ENABLE_SYM = Symbol("enable")
GLOBAL_GAIN_SYM = "gain"
