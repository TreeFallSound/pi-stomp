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

from dataclasses import dataclass
from enum import Enum
import logging
from typing import TypedDict
from common.parameter import Parameter
from rtmidi import MidiOut


class RoutingDestination(Enum):
    VIRTUAL = "virtual"
    EXTERNAL = "external"


@dataclass(frozen=True)
class RoutingInfo:
    destination: RoutingDestination
    port_name: str | None = None

    @classmethod
    def virtual(cls) -> "RoutingInfo":
        return cls(destination=RoutingDestination.VIRTUAL)

    @classmethod
    def external(cls, port_name: str) -> "RoutingInfo":
        return cls(destination=RoutingDestination.EXTERNAL, port_name=port_name)


class AnalogDisplayInfo(TypedDict, total=False):
    type: str | None  # Token.KNOB, Token.EXPRESSION, Token.VOLUME
    id: int | None  # Position on screen (0-based from left); None if unpositioned
    category: str | None
    port_name: str | None  # External port name if routed externally
    midi_cc: int | None  # MIDI CC for external routing display


# Per-pedalboard analog/encoder assignment display, keyed by "instance:param"
# (plugin-bound), "channel:cc" (external), or Token.VOLUME.
AnalogControllers = dict[str, AnalogDisplayInfo]


class Controller:
    type: str | None = None  # class default; not in __init__ — clashes with Encoder.type in EncoderController's MRO

    def __init__(self, midi_channel: int, midi_CC: int | None):
        self.midi_channel: int = midi_channel
        self.midi_CC: int | None = midi_CC
        self.parameter: Parameter | None = None
        self.midi_min: int = 0
        self.midi_max: int = 127
        self.midi_value: int = 0
        self.midiout: MidiOut | None = None

    def set_value(self, value: float) -> None:
        logging.error(f"Controller subclass ({self.__class__.__name__}) hasn't overriden the set_value method")

    def bind_to_parameter(self, parameter: Parameter) -> None:
        self.parameter = parameter
        self.set_value(parameter.value)

    def get_routing_info(self) -> RoutingInfo:
        from modalapi.external_midi import ExternalMidiOut

        if isinstance(self.midiout, ExternalMidiOut):
            return RoutingInfo.external(self.midiout.port_name)
        return RoutingInfo.virtual()

    def get_display_info(self) -> AnalogDisplayInfo:
        routing = self.get_routing_info()
        info: AnalogDisplayInfo = {}
        if routing.destination == RoutingDestination.EXTERNAL:
            info["port_name"] = routing.port_name
            info["midi_cc"] = self.midi_CC
        return info
