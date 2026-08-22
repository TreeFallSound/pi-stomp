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

"""Version 1 of the config file format.

These types mirror the YAML shape. A field holds UNSET when the file does not
contain the key. Two documents merge on the keys that they contain, so an
absent key keeps the lower layer and an explicit null clears the value.

Nothing here knows what the application does with a value. pistomp.config.adapt_v1
turns a merged document into the pistomp.config.model types.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from collections.abc import Callable
from typing import Annotated, Any, Literal, TypeVar

import msgspec
from msgspec import UNSET, Meta, Struct, UnsetType, convert
from msgspec.structs import asdict, replace

from blend.types import BlendSnapshotConfig

data_dir = "/home/pistomp/data/config"

DEFAULT_CONFIG_FILE = "default_config.yml"

MidiCC = Annotated[int, Meta(ge=0, le=127)]
MidiChannel = Annotated[int, Meta(ge=0, le=15)]
FileMidiChannel = Annotated[int, Meta(ge=1, le=16)]


FootswitchDisable = Annotated[
    bool | None | UnsetType, Meta(description="Disable this footswitch entirely or per-pedalboard (disabled=True)")
]

FootswitchMidiPort = Annotated[
    str | None | UnsetType,
    Meta(
        description=(
            "Send MIDI to this external port instead of the virtual MIDI Through port; "
            "falls back to virtual if the device is unavailable (must match a port in external_midi)"
        )
    ),
]

FootswitchMidiChannel = Annotated[
    MidiChannel | None | UnsetType,
    Meta(
        description=(
            "Override MIDI channel for this footswitch; required when midi_port is set, "
            "since external devices rarely share the hardware default channel"
        )
    ),
]

AnalogMidiPort = Annotated[
    str | None | UnsetType,
    Meta(
        description=(
            "Send MIDI to this external port instead of the virtual MIDI Through port; "
            "falls back to virtual if the device is unavailable (must match a port in external_midi)"
        )
    ),
]

AnalogMidiChannel = Annotated[
    MidiChannel | None | UnsetType,
    Meta(
        description=(
            "Override MIDI channel for this controller; required when midi_port is set, "
            "since external devices rarely share the hardware default channel"
        )
    ),
]

EncoderMidiPort = Annotated[
    str | None | UnsetType,
    Meta(
        description=(
            "Send MIDI to this external port instead of the virtual MIDI Through port; "
            "falls back to virtual if the device is unavailable (must be the device name)"
        )
    ),
]

EncoderMidiChannel = Annotated[
    MidiChannel | None | UnsetType,
    Meta(
        description=(
            "Override MIDI channel for this encoder; required when midi_port is set, "
            "since external devices rarely share the hardware default channel"
        )
    ),
]

NoneToken = Literal["None"]
Step = Literal["UP", "DOWN"]
BypassMode = Literal["LEFT", "RIGHT", "LEFT_RIGHT"]
SwitchType = Literal["KNOB", "EXPRESSION"]
EncoderType = Literal["KNOB", "VOLUME"]
TapTempoAction = Literal["set_mod_tap_tempo"]

LongpressName = Literal[
    "next_snapshot",
    "previous_snapshot",
    "toggle_bypass",
    "toggle_tap_tempo_enable",
    "toggle_tuner_enable",
    "next_pedalboard",
    "previous_pedalboard",
]


class LongpressMapping(Struct, frozen=True, forbid_unknown_fields=True):
    """The argument-carrying long-press form. Exactly one key is allowed."""

    midi_CC: MidiCC | UnsetType = UNSET
    preset: int | Step | UnsetType = UNSET
    pedalboard: Step | UnsetType = UNSET

    def __post_init__(self) -> None:
        given = [v for v in asdict(self).values() if v is not UNSET]
        if len(given) != 1:
            raise ValueError("a longpress mapping needs exactly one of midi_CC, preset, pedalboard")


Longpress = LongpressName | list[LongpressName] | LongpressMapping


def _check_routing(midi_port: str | None | UnsetType, midi_channel: int | None | UnsetType) -> None:
    """An external device rarely shares the hardware default channel."""
    if midi_port is not UNSET and midi_port is not None and midi_channel is UNSET:
        raise ValueError("midi_port needs midi_channel")


class FootswitchEntry(Struct, frozen=True, forbid_unknown_fields=True):
    id: int
    adc_input: int | None | UnsetType = UNSET
    gpio_input: int | None | UnsetType = UNSET
    debounce_input: int | None | UnsetType = UNSET
    gpio_output: int | None | UnsetType = UNSET
    ledstrip_position: int | None | UnsetType = UNSET
    tap_tempo: TapTempoAction | None | UnsetType = UNSET
    midi_CC: MidiCC | NoneToken | None | UnsetType = UNSET
    midi_channel: FootswitchMidiChannel = UNSET
    midi_port: FootswitchMidiPort = UNSET
    longpress: Longpress | None | UnsetType = UNSET
    preset: int | Step | None | UnsetType = UNSET
    bypass: BypassMode | None | UnsetType = UNSET
    color: str | None | UnsetType = UNSET
    disable: FootswitchDisable = UNSET

    def __post_init__(self) -> None:
        _check_routing(self.midi_port, self.midi_channel)


class EncoderEntry(Struct, frozen=True, forbid_unknown_fields=True):
    id: int
    type: EncoderType | None | UnsetType = UNSET
    midi_CC: MidiCC | NoneToken | None | UnsetType = UNSET
    midi_channel: EncoderMidiChannel = UNSET
    midi_port: EncoderMidiPort = UNSET
    longpress: str | None | UnsetType = UNSET
    disable: bool | None | UnsetType = UNSET

    def __post_init__(self) -> None:
        _check_routing(self.midi_port, self.midi_channel)


class AnalogEntry(Struct, frozen=True, forbid_unknown_fields=True):
    id: int
    adc_input: int | None | UnsetType = UNSET
    type: SwitchType | None | UnsetType = UNSET
    threshold: Annotated[int, Meta(ge=0, le=127)] | None | UnsetType = UNSET
    autosync: bool | None | UnsetType = UNSET
    midi_CC: MidiCC | NoneToken | None | UnsetType = UNSET
    midi_channel: AnalogMidiChannel = UNSET
    midi_port: AnalogMidiPort = UNSET
    disable: bool | None | UnsetType = UNSET

    def __post_init__(self) -> None:
        _check_routing(self.midi_port, self.midi_channel)


class MidiSection(Struct, frozen=True, forbid_unknown_fields=True):
    channel: FileMidiChannel


class ExternalMidiSection(Struct, frozen=True, forbid_unknown_fields=True):
    enabled: bool | UnsetType = UNSET
    send_delay_ms: Annotated[int, Meta(ge=0)] | UnsetType = UNSET
    messages: dict[str, list[list[Annotated[int, Meta(ge=0, le=255)]]]] | UnsetType = UNSET


class HardwareSection(Struct, frozen=True, forbid_unknown_fields=True):
    version: float | UnsetType = UNSET
    midi: MidiSection | UnsetType = UNSET
    footswitches: list[FootswitchEntry] | None | UnsetType = UNSET
    encoders: list[EncoderEntry] | None | UnsetType = UNSET
    analog_controllers: list[AnalogEntry] | None | UnsetType = UNSET
    external_midi: ExternalMidiSection | None | UnsetType = UNSET


class ConfigDocument(Struct, frozen=True, forbid_unknown_fields=True):
    hardware: HardwareSection | UnsetType = UNSET
    blend_snapshots: list[BlendSnapshotConfig] | None | UnsetType = UNSET


class MergedDocument(Struct, frozen=True):
    version: float | UnsetType
    midi_channel: int | UnsetType
    external_midi: ExternalMidiSection
    blend_snapshots: list[BlendSnapshotConfig]
    footswitches: tuple[FootswitchEntry, ...]
    encoders: tuple[EncoderEntry, ...]
    analog_controllers: tuple[AnalogEntry, ...]


class ConfigError(Exception):
    pass


_E = TypeVar("_E", FootswitchEntry, EncoderEntry, AnalogEntry)
_S = TypeVar("_S", bound=Struct)


def _set_fields(entry: Struct) -> dict[str, Any]:
    return {k: v for k, v in asdict(entry).items() if v is not UNSET}


def _overlaid(base: _S, over: _S) -> _S:
    return replace(base, **_set_fields(over))


def _by_id(entries: list[_E] | None | UnsetType, section: str) -> dict[int, _E]:
    if entries is UNSET or entries is None:
        return {}
    found: dict[int, _E] = {}
    for entry in entries:
        if entry.id in found:
            logging.warning("config: %s has more than one entry with id %d", section, entry.id)
        found[entry.id] = entry
    return found


def _merged_entries(
    base_section: HardwareSection | UnsetType,
    over_section: HardwareSection | UnsetType,
    pick: Callable[[HardwareSection], list[_E] | None | UnsetType],
    name: str,
) -> tuple[_E, ...]:
    base_list = pick(base_section) if base_section is not UNSET else UNSET
    over_list = pick(over_section) if over_section is not UNSET else UNSET
    if over_list is None:
        return ()
    base = _by_id(base_list, name)
    for control_id, entry in _by_id(over_list, name).items():
        if control_id not in base:
            logging.warning("config: %s id %d is not in %s", name, control_id, DEFAULT_CONFIG_FILE)
            continue
        base[control_id] = _overlaid(base[control_id], entry)
    return tuple(base[k] for k in sorted(base))


def _hardware(doc: ConfigDocument | None) -> HardwareSection | UnsetType:
    return doc.hardware if doc is not None else UNSET


def _merged_external_midi(base: HardwareSection | UnsetType, over: HardwareSection | UnsetType) -> ExternalMidiSection:
    if over is not UNSET and over.external_midi is None:
        return ExternalMidiSection()
    sections = [s.external_midi for s in (base, over) if s is not UNSET]
    merged = ExternalMidiSection()
    for section in sections:
        if section is UNSET or section is None:
            continue
        messages = merged.messages if merged.messages is not UNSET else {}
        merged = _overlaid(merged, section)
        if section.messages is not UNSET:
            merged = replace(merged, messages={**messages, **section.messages})
    return merged


def merge(default: ConfigDocument, pedalboard: ConfigDocument | None = None) -> MergedDocument:
    """Overlay a pedalboard document onto the global document."""
    base = _hardware(default)
    over = _hardware(pedalboard)

    blend: list[BlendSnapshotConfig] | None | UnsetType = UNSET
    if pedalboard is not None:
        blend = pedalboard.blend_snapshots
    if blend is UNSET:
        blend = default.blend_snapshots
    if blend is UNSET or blend is None:
        blend = []

    channel: int | UnsetType = UNSET
    for section in (base, over):
        if section is not UNSET and section.midi is not UNSET:
            channel = section.midi.channel

    return MergedDocument(
        version=base.version if base is not UNSET else UNSET,
        midi_channel=channel,
        external_midi=_merged_external_midi(base, over),
        blend_snapshots=blend,
        footswitches=_merged_entries(base, over, lambda s: s.footswitches, "footswitches"),
        encoders=_merged_entries(base, over, lambda s: s.encoders, "encoders"),
        analog_controllers=_merged_entries(base, over, lambda s: s.analog_controllers, "analog_controllers"),
    )


def parse(raw: Any, source: str | Path) -> ConfigDocument:
    """Build a document from already-loaded YAML data."""
    try:
        return convert(raw if raw is not None else {}, ConfigDocument)
    except msgspec.ValidationError as e:
        raise ConfigError("Config file error in %s: %s" % (source, e)) from None


def load_cfg_from_file(path: str | Path) -> ConfigDocument:
    """Load and validate a config from an explicit file path."""
    with open(path, "rb") as f:
        return parse(msgspec.yaml.decode(f.read()), path)


def load_default_cfg() -> ConfigDocument:
    """Load and validate the global default_config.yml."""
    return load_cfg_from_file(os.path.join(data_dir, DEFAULT_CONFIG_FILE))


def read_bundle_config(bundle: str | Path | None) -> ConfigDocument | None:
    """Read the optional config.yml of a pedalboard bundle.

    A broken pedalboard config is not fatal. The pedalboard then runs on the
    global defaults alone.
    """
    if bundle is None:
        return None
    path = Path(bundle) / "config.yml"
    if not path.exists():
        return None
    try:
        return load_cfg_from_file(path)
    except (OSError, ConfigError, msgspec.DecodeError):
        logging.exception("config: ignoring %s", path)
        return None


def hardware_version(document: ConfigDocument) -> float | None:
    """The hardware version that selects the handler and hardware classes."""
    if document.hardware is UNSET or document.hardware.version is UNSET:
        return None
    return document.hardware.version


def json_schema() -> dict[str, Any]:
    """The JSON Schema of this format, generated from the types above."""
    return msgspec.json.schema(ConfigDocument)
