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

from dataclasses import dataclass, field

from common.parameter import Parameter
from modalapi.pedalboard import Pedalboard
from modalapi.plugin import Plugin
from pistomp.controller import AnalogControllers, Controller
from pistomp.footswitch import Footswitch


@dataclass
class Current:
    """The active pedalboard, and the runtime associations that it owns.

    `close` releases the associations. The code that binds must close.
    """

    pedalboard: Pedalboard
    presets: dict[int, str] = field(default_factory=dict)
    preset_index: int = 0  # Assumes pedalboard loads at snapshot 0 (default behavior)
    analog_controllers: AnalogControllers = field(default_factory=dict)
    _controllers: list[Controller] = field(default_factory=list)
    _plugin_bindings: list[tuple[Plugin, Controller]] = field(default_factory=list)

    def bind(self, controller: Controller, parameter: Parameter) -> None:
        controller.bind_to_parameter(parameter)
        self.track(controller)

    def attach(self, controller: Controller, parameter: Parameter) -> None:
        controller.parameter = parameter
        self.track(controller)

    def track(self, controller: Controller) -> None:
        if controller not in self._controllers:
            self._controllers.append(controller)

    def track_plugin_binding(self, plugin: Plugin, controller: Controller) -> None:
        self.track(controller)
        binding = (plugin, controller)
        if binding not in self._plugin_bindings:
            self._plugin_bindings.append(binding)

    def close(self) -> None:
        for plugin, controller in reversed(self._plugin_bindings):
            if controller in plugin.controllers:
                plugin.controllers.remove(controller)
            plugin.has_footswitch = any(isinstance(c, Footswitch) for c in plugin.controllers)
        for controller in reversed(self._controllers):
            controller.unbind_from_parameter()
        self._plugin_bindings.clear()
        self._controllers.clear()
        self.analog_controllers = {}
