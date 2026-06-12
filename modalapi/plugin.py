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
# You should have not received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import json

from common.parameter import Parameter
from pistomp.footswitch import Footswitch

Point = tuple[int, int]

# v1 LCDs store (x, y, zone); v2+ LCDs store (xy1, xy2, zone)
LcdPosition = tuple[int, int, int] | tuple[Point, Point, int]


class Plugin:
    def __init__(
        self,
        instance_id: str,
        parameters: dict[str, Parameter],
        info: dict | None,
        category: str | None = None,
        uri: str | None = None,
    ) -> None:
        self.instance_id: str = instance_id.lstrip("/")
        self.parameters: dict[str, Parameter] = parameters
        self.bypass_indicator_xy: tuple[Point, Point] = ((0, 0), (0, 0))
        self.lcd_xyz: LcdPosition | None = None
        self.controllers: list[Footswitch] = []
        self.has_footswitch: bool = False
        self.category: str | None = category
        # LV2 plugin URI (e.g. "http://gareus.org/oss/lv2/fil4#mono").
        # Used by full-screen panels that override the generic parameter menu.
        self.uri: str | None = uri
        # Snapshot of parameter values at pedalboard parse time. Cleared on
        # pedalboard reload. Serves as the baseline for panel Reset.
        self.pedalboard_snapshot: dict[str, float] = {}

    def is_bypassed(self) -> bool:
        param = self.parameters.get(":bypass")
        if param is not None:
            return bool(param.value)
        return True

    def toggle_bypass(self) -> float:
        param = self.parameters.get(":bypass")
        if param is None:
            return 0.0
        new_value = 0.0 if param.value else 1.0
        param.value = new_value
        return new_value

    def set_bypass(self, bypass: bool) -> None:
        param = self.parameters.get(":bypass")
        if param is None:
            return
        param.value = 1.0 if bypass else 0.0
        if self.has_footswitch:
            for c in self.controllers:
                if isinstance(c, Footswitch):
                    c.set_value(param.value)

    def to_json(self) -> str:
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)
