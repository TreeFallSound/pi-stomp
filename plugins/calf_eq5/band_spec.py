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

from __future__ import annotations

from plugins.eq.band_spec import BandSpec
from common.parameter import Symbol

_COLORS: dict[str, tuple[int, int, int]] = {
    "LS": (255, 180, 80),
    "P1": (255, 230, 80),
    "P2": (130, 220, 110),
    "P3": (80, 180, 255),
    "HS": (210, 130, 230),
}

BAND_SPECS: tuple[BandSpec, ...] = (
    BandSpec("LS", "shelf", Symbol("ls_active"), Symbol("ls_freq"), Symbol("ls_q"), Symbol("ls_level"), "low",
             10.0, 20000.0, 0.1, 10.0, color=_COLORS["LS"], q_units="q", gain_min=-40.0, gain_max=14.0),
    BandSpec("P1", "peak", Symbol("p1_active"), Symbol("p1_freq"), Symbol("p1_q"), Symbol("p1_level"), None,
             10.0, 20000.0, 0.1, 100.0, color=_COLORS["P1"], q_units="q", gain_min=-40.0, gain_max=14.0),
    BandSpec("P2", "peak", Symbol("p2_active"), Symbol("p2_freq"), Symbol("p2_q"), Symbol("p2_level"), None,
             10.0, 20000.0, 0.1, 100.0, color=_COLORS["P2"], q_units="q", gain_min=-40.0, gain_max=14.0),
    BandSpec("P3", "peak", Symbol("p3_active"), Symbol("p3_freq"), Symbol("p3_q"), Symbol("p3_level"), None,
             10.0, 20000.0, 0.1, 100.0, color=_COLORS["P3"], q_units="q", gain_min=-40.0, gain_max=14.0),
    BandSpec("HS", "shelf", Symbol("hs_active"), Symbol("hs_freq"), Symbol("hs_q"), Symbol("hs_level"), "high",
             10.0, 20000.0, 0.1, 10.0, color=_COLORS["HS"], q_units="q", gain_min=-40.0, gain_max=14.0),
)
