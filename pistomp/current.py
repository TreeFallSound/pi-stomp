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
    _control_by_param: dict[Parameter, Controller] = field(default_factory=dict)

    def bind(self, controller: Controller, parameter: Parameter) -> None:
        self._release(controller)
        controller.bind_to_parameter(parameter)
        self._control_by_param[parameter] = controller
        self.track(controller)

    def attach(self, controller: Controller, parameter: Parameter) -> None:
        self._release(controller)
        controller.parameter = parameter
        self._control_by_param[parameter] = controller
        self.track(controller)

    def control_for(self, parameter: Parameter) -> Controller | None:
        """The control bound to this parameter. A CC number is an address, not
        an identity: two parameters can name the same one, so the binder's
        decision is the record and this is how to read it."""
        return self._control_by_param.get(parameter)

    def _release(self, controller: Controller) -> None:
        prior = controller.parameter
        if prior is not None and self._control_by_param.get(prior) is controller:
            del self._control_by_param[prior]

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
        for controller in reversed(self._controllers):
            controller.unbind_from_parameter()
        self._plugin_bindings.clear()
        self._controllers.clear()
        self._control_by_param.clear()
        self.analog_controllers = {}
