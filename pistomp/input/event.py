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

"""Event dataclasses dispatched into InputSinks. See INPUT_ROUTER.md."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pistomp.controller import Controller


class SwitchEventKind(Enum):
    PRESS = auto()
    LONGPRESS = auto()


@dataclass
class ControllerEvent:
    controller: "Controller"


@dataclass
class EncoderEvent(ControllerEvent):
    # Raw detents this tick; positive = clockwise.
    rotations: int = 0
    # Speed amplification used to compute new_value (diagnostic).
    multiplier: float = 1.0
    # Already-quantized parameter value (encoder advanced its own state).
    new_value: float = 0.0
    # Already-renormalized MIDI value [0-127].
    new_midi_value: int = 0


@dataclass
class AnalogEvent(ControllerEvent):
    # Raw ADC reading (0-1023 for MCP3008).
    raw_value: int = 0
    # Already-converted MIDI value [0-127].
    midi_value: int = 0


@dataclass
class SwitchEvent(ControllerEvent):
    kind: SwitchEventKind = SwitchEventKind.PRESS
    timestamp: float = 0.0
