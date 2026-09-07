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
from enum import Enum, StrEnum
from typing import TYPE_CHECKING, TypedDict

import common.util as util
from common.parameter import Parameter

if TYPE_CHECKING:
    from pistomp.input.sink import InputSink


class ControlType(StrEnum):
    """What a control does. Only KNOB, EXPRESSION and VOLUME come from a config
    file; NAV is a fixed property of the hardware."""

    KNOB = "KNOB"
    EXPRESSION = "EXPRESSION"
    VOLUME = "VOLUME"
    NAV = "nav"


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
    type: ControlType | None  # KNOB, EXPRESSION, or VOLUME
    id: int | None  # Position on screen (0-based from left); None if unpositioned
    category: str | None
    port_name: str | None  # External port name if routed externally
    midi_cc: int | None  # MIDI CC for external routing display


# Per-pedalboard analog/encoder assignment display, keyed by "instance:param"
# (plugin-bound), "channel:cc" (external), or ControlType.VOLUME.
AnalogControllers = dict[str, AnalogDisplayInfo]


class Controller:
    type: ControlType | None = None
    id: int | None = None  # position/identifier for display routing or event filtering

    def __init__(self, midi_channel: int, midi_CC: int | None):
        self.midi_channel: int = midi_channel
        self.midi_CC: int | None = midi_CC
        self.parameter: Parameter | None = None
        self.disabled = False
        # type is not declared here — it conflicts with Encoder's MRO.
        # Subclasses that carry type must declare it themselves.
        self.midi_min: int = 0
        self.midi_max: int = 127
        self.midi_value: int = 0
        self._sink: InputSink | None = None
        self._unsub_param: Callable[[], None] | None = None

    @property
    def sink(self) -> InputSink:
        assert self._sink is not None, f"{self.__class__.__name__}.sink accessed before register_sink() was called"
        return self._sink

    @sink.setter
    def sink(self, value: InputSink | None) -> None:
        self._sink = value

    def bind_to_parameter(self, parameter: Parameter) -> None:
        self.unbind_from_parameter()
        self.parameter = parameter

    def unbind_from_parameter(self) -> None:
        if self._unsub_param is not None:
            self._unsub_param()
            self._unsub_param = None
        self.parameter = None

    def to_midi(self, value: float) -> int:
        """Convert a bound-parameter value to this control's 7-bit CC byte. The
        MIDI mechanics (range, channel, routing) are the controller's, not the
        param's — the param stays MIDI-agnostic."""
        assert self.parameter is not None, "to_midi is bound-only; requires a parameter"
        # mod-host maps the CC back onto the port with the port's own taper, so a
        # logarithmic port needs the geometric inverse
        position = util.to_normalized(
            value, self.parameter.minimum, self.parameter.maximum, self.parameter.is_logarithmic
        )
        midi_value = round(util.from_normalized(position, self.midi_min, self.midi_max))
        return int(max(0, min(127, midi_value)))

    def bar_midi_value(self) -> int:
        """0-127 for the LCD bar, derived from the parameter (the owner)."""
        assert self.parameter is not None, "bar_midi_value is bound-only; requires a parameter"
        return self.to_midi(self.parameter.value)

    def get_display_info(self) -> AnalogDisplayInfo:
        """Own-presentation only; routing-derived fields are added by the
        registry owner (ControllerManager._bind_external_controllers)."""
        return {}


class StatefulController(Controller):
    """A controller that holds its own copy of the bound parameter's value as
    presentation state — a footswitch's LED/toggle, a pot's last MIDI reading —
    and so must be told when the value changes externally (Plugin.set_param_value
    on a mod-ui echo). Encoders are deliberately stateless: they own no copy of
    the value, report only deltas, and so echoes skip them."""

    def set_value(self, value: float) -> None:
        raise NotImplementedError

    def bind_to_parameter(self, parameter: Parameter) -> None:
        super().bind_to_parameter(parameter)
        self.set_value(parameter.value)
        # The keycap mirrors committed values — a mod-ui echo or a menu/dialog
        # commit — but not a bare preview: a local press updates its own toggle
        # and LED, then waits for the echo to refresh. Neither write path needs
        # to know the controller exists.
        self._unsub_param = parameter.on_commit(lambda p: self.set_value(p.value))
