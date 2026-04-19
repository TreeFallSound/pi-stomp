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
import json
import logging
from typing import TypedDict
from common.parameter import Parameter
from rtmidi import MidiOut


class RoutingDestination(Enum):
    """Where MIDI messages are routed."""
    VIRTUAL = "virtual"      # MIDI through virtual port
    EXTERNAL = "external"    # External hardware device


@dataclass(frozen=True)
class RoutingInfo:
    """Immutable routing information for a controller."""
    destination: RoutingDestination
    port_name: str | None = None  # Only for EXTERNAL destination

    @classmethod
    def virtual(cls) -> 'RoutingInfo':
        """Factory for virtual port routing."""
        return cls(destination=RoutingDestination.VIRTUAL)

    @classmethod
    def external(cls, port_name: str) -> 'RoutingInfo':
        """Factory for external port routing."""
        return cls(destination=RoutingDestination.EXTERNAL, port_name=port_name)


class AnalogDisplayInfo(TypedDict, total=False):
    """Display information for analog controls and encoders."""
    type: str           # Token.KNOB, Token.EXPRESSION, Token.VOLUME
    id: int             # Position on screen (0-based from left)
    category: str | None  # Plugin category (for color coding) or None
    port_name: str | None  # External port name if routed externally
    midi_cc: int | None    # MIDI CC for external routing display


class FootswitchDisplayInfo(TypedDict, total=False):
    """Display information for footswitches."""
    id: int
    label: str | None
    color: tuple[int, int, int] | None  # RGB
    category: str | None


class Controller:

    def __init__(self, midi_channel: int, midi_CC: int | None):
        self.midi_channel: int = midi_channel
        self.midi_CC: int | None = midi_CC
        self.parameter: Parameter | None = None
        self.hardware_name = None
        #self.type = None  # this will conflict with encoder.type for EncoderController
        self.midi_min: int = 0
        self.midi_max: int = 127
        self.midiout: MidiOut | None = None  # Set by subclasses

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)

    def set_value(self, value):
        logging.error("Controller subclass hasn't overriden the set_value method")

    def get_routing_info(self) -> RoutingInfo:
        """Get routing information for this controller."""
        from modalapi.external_midi import ExternalMidiOut
        if isinstance(self.midiout, ExternalMidiOut):
            return RoutingInfo.external(self.midiout.port_name)
        else:
            return RoutingInfo.virtual()

    def get_display_info(self) -> dict:
        """Get display information. Supplement in subclasses."""
        routing = self.get_routing_info()
        info: dict = {}
        if routing.destination == RoutingDestination.EXTERNAL:
            info['port_name'] = routing.port_name
            info['midi_cc'] = self.midi_CC
        return info
