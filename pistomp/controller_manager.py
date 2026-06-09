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
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import logging
from typing import cast, TYPE_CHECKING

import common.token as Token
from pistomp.analogmidicontrol import AnalogMidiControl
from pistomp.controller import AnalogDisplayInfo
from pistomp.current import Current
from pistomp.encodermidicontrol import EncoderMidiControl
from pistomp.footswitch import Footswitch

if TYPE_CHECKING:
    from pistomp.hardware import Hardware


class ControllerManager:
    """
    Manages controller/parameter bindings on the current pedalboard,
    overlaying per-pedalboard config on top of the base.
    Version differences are passed as flags rather than subclassed:

      reorder_footswitch_plugins  v1 moves footswitch-controlled plugins to the
                                  tail of the chain; v3 leaves order untouched.
    """

    def __init__(
        self,
        hardware: "Hardware",
        *,
        reorder_footswitch_plugins: bool = False,
    ):
        self._hw = hardware
        self._reorder_footswitch_plugins = reorder_footswitch_plugins

    def bind(self, current: Current | None) -> None:
        """Rebind all controllers for the active pedalboard state."""
        if current is None:
            return

        # Clear previous parameter bindings from all controllers except volume.
        for controller in self._hw.controllers.values():
            if controller.type != Token.VOLUME:
                controller.parameter = None

        current.analog_controllers = {}

        if current.pedalboard:
            footswitch_plugins = self._bind_plugin_parameters(current)
            self._bind_volume_encoders(current)
            if self._reorder_footswitch_plugins:
                self._move_footswitch_plugins_to_end(current, footswitch_plugins)

        self._bind_external_controllers(current)

    def _bind_plugin_parameters(self, current) -> list:
        """Bind controllers referenced by plugin parameters; return the plugins
        that gained a footswitch."""
        footswitch_plugins = []
        for plugin in current.pedalboard.plugins:
            if plugin is None or plugin.parameters is None:
                continue
            for param in plugin.parameters.values():
                if param.binding is None:
                    continue
                controller = self._hw.controllers.get(param.binding)
                if controller is None:
                    continue

                # External controllers aren't bound to plugin parameters.
                if self._hw.is_external(controller):
                    logging.warning(
                        f"Plugin parameter {plugin.name}:{param.name} is bound to external controller "
                        f"{param.binding} (routed to {self._hw.external_port_name(controller)}) - ignoring plugin binding"
                    )
                    continue

                controller.parameter = param
                controller.set_value(param.value)
                plugin.controllers.append(controller)

                if isinstance(controller, Footswitch):
                    plugin.has_footswitch = True
                    footswitch_plugins.append(plugin)
                    controller.set_category(plugin.category)
                elif isinstance(controller, (AnalogMidiControl, EncoderMidiControl)):
                    key = "%s:%s" % (plugin.instance_id, param.name)
                    controller.cfg[Token.CATEGORY] = plugin.category  # somewhat LAME adding to cfg dict
                    controller.cfg[Token.TYPE] = controller.type
                    controller.cfg[Token.ID] = controller.id
                    current.analog_controllers[key] = cast(AnalogDisplayInfo, controller.cfg)
        return footswitch_plugins

    def _bind_volume_encoders(self, current) -> None:
        """Surface VOLUME-type encoders in the assignment display (v3 only in
        practice — v1 has no VOLUME-typed encoder)."""
        for e in self._hw.encoders:
            if e.type == Token.VOLUME:
                entry: AnalogDisplayInfo = {"category": None, "type": e.type, "id": e.id}
                current.analog_controllers[Token.VOLUME] = entry

    @staticmethod
    def _move_footswitch_plugins_to_end(current, footswitch_plugins) -> None:
        plugins = current.pedalboard.plugins
        current.pedalboard.plugins = [p for p in plugins if p.has_footswitch is False] + footswitch_plugins

    def _bind_external_controllers(self, current) -> None:
        """Externally-routed controllers: bind a synthetic parameter and show
        them under an "External" category."""
        for controller in self._hw.controllers.values():
            if not self._hw.is_external(controller) or controller.midi_CC is None:
                continue
            port_name = self._hw.external_port_name(controller)

            controller.parameter = self._hw.create_external_parameter(
                controller, port_name, controller.midi_channel, controller.midi_CC
            )

            if not isinstance(controller, (AnalogMidiControl, EncoderMidiControl)):
                continue
            key = f"{controller.midi_channel}:{controller.midi_CC}"
            # Seed type/id (the encoder's get_display_info is empty); routing
            # fields come from the registry, not the control.
            entry: AnalogDisplayInfo = {
                "type": controller.type,
                "id": controller.id,
                **controller.get_display_info(),
                "port_name": port_name,
                "midi_cc": controller.midi_CC,
                "category": "External",
            }
            current.analog_controllers[key] = entry
