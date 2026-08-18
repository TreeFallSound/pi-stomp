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

from collections.abc import Callable
from dataclasses import dataclass
from common.parameter import Symbol


@dataclass(frozen=True)
class ArcSpec:
    symbol: Symbol
    label: str
    color: tuple[int, int, int]
    display_fn: Callable[[float], str]


@dataclass(frozen=True)
class CompressorSpec:
    thr_sym: Symbol
    rat_sym: Symbol
    mak_sym: Symbol
    kn_sym: Symbol | None = None
    in_audio_sym: str = "lv2_audio_in_1"
    out_audio_sym: str = "lv2_audio_out_1"


def build_arc_specs(spec: CompressorSpec) -> tuple[ArcSpec, ...]:
    arcs = [
        ArcSpec(spec.thr_sym, "THRESH", (255, 180, 80), lambda v: f"{v:+.0f}"),
        ArcSpec(spec.rat_sym, "RATIO", (130, 220, 110), lambda v: f"{v:.1f}:1"),
    ]
    if spec.kn_sym is not None:
        arcs.append(ArcSpec(spec.kn_sym, "KNEE", (110, 200, 230), lambda v: f"{v:.1f}"))
    arcs.append(ArcSpec(spec.mak_sym, "MAKEUP", (210, 130, 230), lambda v: f"+{v:.0f}"))
    return tuple(arcs)


_ARC_CENTERS_4: tuple[tuple[int, int], ...] = ((41, 34), (95, 76), (41, 118), (95, 160))
_ARC_CENTERS_3: tuple[tuple[int, int], ...] = ((41, 34), (95, 97), (41, 160))


def arc_centers_for(n: int) -> tuple[tuple[int, int], ...]:
    return _ARC_CENTERS_3 if n == 3 else _ARC_CENTERS_4
