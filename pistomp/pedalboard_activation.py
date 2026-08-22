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

from typing import TYPE_CHECKING, Protocol, cast

from common.contexts import ContextStack
from common.parameter import Parameter
from pistomp.controller import Controller

if TYPE_CHECKING:
    from modalapi.pedalboard import Pedalboard
    from pistomp.config.model import PedalboardConfig


class _PluginBindingOwner(Protocol):
    controllers: list[Controller]
    has_footswitch: bool


class PedalboardActivation:
    """Own runtime associations for one active pedalboard."""

    def __init__(self, pedalboard: "Pedalboard", config: "PedalboardConfig") -> None:
        self.pedalboard = pedalboard
        self.config = config
        self.effective_table = ContextStack(layers=[])
        self._bound_controllers: list[Controller] = []
        self._plugin_bindings: list[tuple[_PluginBindingOwner, Controller]] = []
        self._closed = False

    def bind(self, controller: Controller, parameter: Parameter) -> None:
        controller.bind_to_parameter(parameter)
        self.track_controller(controller)

    def attach(self, controller: Controller, parameter: Parameter) -> None:
        controller.parameter = parameter
        self.track_controller(controller)

    def track_controller(self, controller: Controller) -> None:
        if controller not in self._bound_controllers:
            self._bound_controllers.append(controller)

    def track_plugin_binding(self, plugin: object, controller: Controller) -> None:
        self.track_controller(controller)
        binding = (cast(_PluginBindingOwner, plugin), controller)
        if binding not in self._plugin_bindings:
            self._plugin_bindings.append(binding)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        from pistomp.footswitch import Footswitch

        for plugin, controller in reversed(self._plugin_bindings):
            if controller in plugin.controllers:
                plugin.controllers.remove(controller)
            plugin.has_footswitch = any(isinstance(bound, Footswitch) for bound in plugin.controllers)

        for controller in reversed(self._bound_controllers):
            controller.unbind_from_parameter()

        self._plugin_bindings.clear()
        self._bound_controllers.clear()
        self.effective_table = ContextStack(layers=[])
