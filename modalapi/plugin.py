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
import re
from dataclasses import replace
from typing import TYPE_CHECKING

from common.color import RectBorder
from common.parameter import Parameter
from modalapi.plugin_customization import PluginCustomization, PluginExtraData
from pistomp.controller import Controller

if TYPE_CHECKING:
    from plugins.base import PluginPanel

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
        customization: PluginCustomization | None = None,
        extra_data: PluginExtraData | None = None,
        instance_number: int | None = None,
    ) -> None:
        self.instance_id: str = instance_id.lstrip("/")
        # mod-host's numeric instance (pedal:instanceNumber). Names its JACK
        # ports "effect_<N>:<symbol>", so panels that tap a plugin's audio need it.
        self.instance_number: int | None = instance_number
        self.info: dict | None = info
        self.name: str = (info or {}).get("name") or self.instance_id
        self.parameters: dict[str, Parameter] = parameters
        self.canvas_x: float = 0.0
        self.canvas_y: float = 0.0
        self.bypass_indicator_xy: tuple[Point, Point] = ((0, 0), (0, 0))
        self.lcd_xyz: LcdPosition | None = None
        self.controllers: list[Controller] = []
        self.has_footswitch: bool = False
        self.category: str | None = category
        self.uri: str | None = uri
        self.pedalboard_snapshot: dict[str, float] = {}
        c: PluginCustomization = customization or PluginCustomization()
        if extra_data is not None:
            c = replace(c, extra_data=extra_data)
        self.customization: PluginCustomization = c

    @property
    def extra_data(self) -> PluginExtraData | None:
        return self.customization.extra_data

    @property
    def display_name(self) -> str:
        c = self.customization
        if c.display_name_fn:
            override = c.display_name_fn(self)
            if override is not None:
                return override
        if c.display_name:
            return c.display_name
        return self._heuristic_name()

    def _heuristic_name(self) -> str:
        id_base = re.sub(r"_?\d+$", "", self.instance_id).lower()
        raw = self.name if len(self.name) < len(self.instance_id) or id_base in ("mono", "stereo") else self.instance_id
        return raw.replace("_", "")

    @property
    def subtitle(self) -> str | None:
        c = self.customization
        if c.subtitle_fn:
            return c.subtitle_fn(self)
        return None

    @property
    def tile_active_color(self) -> tuple[int, int, int] | None:
        return self.customization.tile_active_color

    @property
    def tile_border(self) -> RectBorder | None:
        return self.customization.tile_border

    @property
    def panel_cls(self) -> type[PluginPanel] | None:
        return self.customization.panel_cls

    @property
    def intercept_shortpress(self) -> bool:
        return self.customization.intercept_shortpress

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

    def set_param_value(self, symbol: str, value: float) -> None:
        """Cache a param's value and mirror it onto any control bound to it, so
        a footswitch's LED/keycap (or a knob/encoder's cached position) tracks
        mod-ui's live value. set_value is polymorphic per control type."""
        param = self.parameters.get(symbol)
        if param is None:
            return
        param.value = value
        for c in self.controllers:
            if c.parameter is param:
                c.set_value(value)

    def set_bypass(self, bypass: bool) -> None:
        self.set_param_value(":bypass", 1.0 if bypass else 0.0)

    def to_json(self) -> str:
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)
