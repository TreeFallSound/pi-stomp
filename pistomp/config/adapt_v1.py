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

"""Turn a version 1 document into the types that the application reads.

The built-in defaults live here, because a later file format can default
differently. UNSET does not cross this boundary.
"""

from __future__ import annotations

from typing import TypeVar

from msgspec import UNSET, UnsetType

from modalapi.external_midi import ExternalMidiConfig
from pistomp.config import schema_v1 as v1
from pistomp.config.model import (
    AnalogBinding,
    ControlType,
    EncoderBinding,
    FootswitchBinding,
    LongpressBoard,
    LongpressMidiCC,
    LongpressPreset,
    LongpressSpec,
    PedalboardConfig,
    PresetAction,
    PresetStep,
)

_T = TypeVar("_T")

RELAY_BYPASS = ("LEFT", "LEFT_RIGHT")


def _value(value: _T | None | UnsetType, default: _T) -> _T:
    """Read a field that cannot hold null. Absent and null give the default."""
    if value is UNSET or value is None:
        return default
    return value


def _nullable(value: _T | None | UnsetType) -> _T | None:
    """Read a field where null clears the value."""
    return None if value is UNSET else value


def _midi_cc(value: int | str | None | UnsetType) -> int | None:
    """The string 'None' and null both mean no CC."""
    if value is UNSET or value is None or isinstance(value, str):
        return None
    return value


def _longpress(value: v1.Longpress | None | UnsetType) -> LongpressSpec | None:
    if value is UNSET or value is None:
        return None
    if not isinstance(value, v1.LongpressMapping):
        return value  # str or list[str]
    if value.midi_CC is not UNSET:
        return LongpressMidiCC(cc=value.midi_CC)
    if value.preset is not UNSET and value.preset is not None:
        p = value.preset
        return LongpressPreset(preset=PresetStep(p) if isinstance(p, str) else p)
    return LongpressBoard(direction=str(value.pedalboard))


def _preset(value: int | str | None | UnsetType) -> PresetAction | None:
    if value is UNSET or value is None:
        return None
    return PresetStep(value) if isinstance(value, str) else value


def _footswitch(entry: v1.FootswitchEntry, midi_channel: int) -> FootswitchBinding:
    return FootswitchBinding(
        id=entry.id,
        adc_input=_nullable(entry.adc_input),
        gpio_input=_nullable(entry.gpio_input),
        debounce_input=_nullable(entry.debounce_input),
        gpio_output=_nullable(entry.gpio_output),
        ledstrip_position=_nullable(entry.ledstrip_position),
        tap_tempo=_nullable(entry.tap_tempo),
        midi_CC=_midi_cc(entry.midi_CC),
        midi_channel=_value(entry.midi_channel, midi_channel),
        midi_port=_nullable(entry.midi_port),
        longpress=_longpress(entry.longpress),
        preset=_preset(entry.preset),
        uses_relay=_nullable(entry.bypass) in RELAY_BYPASS,
        color=_nullable(entry.color),
        disable=_value(entry.disable, False),
    )


def _encoder(entry: v1.EncoderEntry, midi_channel: int) -> EncoderBinding:
    control_type = ControlType(_value(entry.type, ControlType.KNOB))
    return EncoderBinding(
        id=entry.id,
        type=control_type,
        midi_CC=None if control_type is ControlType.VOLUME else _midi_cc(entry.midi_CC),
        midi_channel=_value(entry.midi_channel, midi_channel),
        midi_port=_nullable(entry.midi_port),
        longpress=_nullable(entry.longpress),
        disable=_value(entry.disable, False),
    )


def _analog_control(entry: v1.AnalogEntry, midi_channel: int) -> AnalogBinding:
    return AnalogBinding(
        id=entry.id,
        adc_input=_nullable(entry.adc_input),
        type=ControlType(_value(entry.type, ControlType.KNOB)),
        threshold=_value(entry.threshold, 16),
        autosync=_value(entry.autosync, False),
        midi_CC=_midi_cc(entry.midi_CC),
        midi_channel=_value(entry.midi_channel, midi_channel),
        midi_port=_nullable(entry.midi_port),
        disable=_value(entry.disable, False),
    )


def _external_midi(section: v1.ExternalMidiSection) -> ExternalMidiConfig:
    return ExternalMidiConfig(
        enabled=_value(section.enabled, False),
        send_delay_ms=_value(section.send_delay_ms, 10),
        messages=_value(section.messages, {}),
    )


def adapt(document: v1.MergedDocument) -> PedalboardConfig:
    """Apply the built-in defaults and normalise the file vocabulary."""
    file_channel = _value(document.midi_channel, 1)
    # mod reads a channel one higher than sent, so the file value is 1-based.
    midi_channel = file_channel - 1 if file_channel > 0 else 0
    return PedalboardConfig(
        version=_value(document.version, 0.0),
        midi_channel=midi_channel,
        external_midi=_external_midi(document.external_midi),
        blend_snapshots=document.blend_snapshots,
        footswitches=tuple(_footswitch(e, midi_channel) for e in document.footswitches),
        encoders=tuple(_encoder(e, midi_channel) for e in document.encoders),
        analog_controls=tuple(_analog_control(e, midi_channel) for e in document.analog_controllers),
    )
