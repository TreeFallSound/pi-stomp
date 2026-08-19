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

"""How far a looping plugin is through its loop, as the footswitch strip draws it.

Shared between the renderer that derives it (`modalapi.led_render`) and the
widget that paints it (`uilib.footswitch`), which sit on opposite sides of the
module DAG.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class LoopFill(Enum):
    FILL = auto()  # determinate: `position` of the perimeter is behind us
    STATIC = auto()  # the loop exists but isn't moving
    CHASE = auto()  # length unknown: a head sweeping at `position`


@dataclass(frozen=True)
class LoopProgress:
    mode: LoopFill
    color: tuple[int, int, int]
    segments: int  # bars in the loop; 0 when the length isn't known yet
    position: float = 0.0  # turns, [0, 1)
