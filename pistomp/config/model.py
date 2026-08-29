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

"""The control configuration that the application reads.

Every field holds a value. The file format, the merge of the layers and the
built-in defaults are not visible here. An adapter module builds these types
from one schema version, so a new file format changes the adapter only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from blend.types import BlendSnapshotConfig
from modalapi.external_midi import ExternalMidiConfig
from pistomp.controller import ControlType


class PresetStep(StrEnum):
    UP = "UP"
    DOWN = "DOWN"


PresetAction: TypeAlias = PresetStep | int


# U+2212: the ASCII hyphen is half the width of "+" and reads as a dash, not
# an operator, next to it.
MINUS = "−"


@dataclass(frozen=True)
class LongpressMidiCC:
    cc: int

    def label(self) -> str:
        return f"MIDI CC {self.cc}"


@dataclass(frozen=True)
class LongpressPreset:
    preset: PresetAction

    def label(self) -> str:
        match self.preset:
            case PresetStep.UP:
                return "Snapshot +"
            case PresetStep.DOWN:
                return f"Snapshot {MINUS}"
            case _:
                return f"Snapshot {self.preset}"


@dataclass(frozen=True)
class LongpressBoard:
    direction: str

    def label(self) -> str:
        return "Pedalboard +" if self.direction == PresetStep.UP else f"Pedalboard {MINUS}"


# The mapping form of longpress. The chord form is a tuple of action names.
LongpressAction: TypeAlias = LongpressMidiCC | LongpressPreset | LongpressBoard
LongpressSpec: TypeAlias = tuple[str, ...] | LongpressAction


@dataclass(frozen=True)
class FootswitchBinding:
    id: int
    adc_input: int | None
    gpio_input: int | None
    debounce_input: int | None
    gpio_output: int | None
    ledstrip_position: int | None
    tap_tempo: str | None
    midi_CC: int | None
    midi_channel: int
    midi_port: str | None
    longpress: LongpressSpec | None
    preset: PresetAction | None
    uses_relay: bool
    color: str | None
    disable: bool


@dataclass(frozen=True)
class EncoderBinding:
    id: int
    type: ControlType
    midi_CC: int | None
    midi_channel: int
    midi_port: str | None
    longpress: str | None
    disable: bool


@dataclass(frozen=True)
class AnalogBinding:
    id: int
    adc_input: int | None
    type: ControlType
    threshold: int
    autosync: bool
    midi_CC: int | None
    midi_channel: int
    midi_port: str | None
    disable: bool


@dataclass(frozen=True)
class PedalboardConfig:
    version: float
    midi_channel: int
    external_midi: ExternalMidiConfig
    blend_snapshots: tuple[BlendSnapshotConfig, ...]
    footswitches: tuple[FootswitchBinding, ...]
    encoders: tuple[EncoderBinding, ...]
    analog_controls: tuple[AnalogBinding, ...]

    def footswitch(self, control_id: int) -> FootswitchBinding | None:
        return next((f for f in self.footswitches if f.id == control_id), None)

    def encoder(self, control_id: int) -> EncoderBinding | None:
        return next((e for e in self.encoders if e.id == control_id), None)

    def analog_control(self, control_id: int) -> AnalogBinding | None:
        return next((a for a in self.analog_controls if a.id == control_id), None)
