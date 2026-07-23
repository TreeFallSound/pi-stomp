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

"""
Type-safe WebSocket protocol for MOD-UI communication.

Defines message types received from mod-ui WebSocket server.
"""

from dataclasses import dataclass
from typing import Literal, Union, cast
import logging

from common.parameter import Symbol

# mod-ui's transport broadcast carries a syncMode token drawn from this
# closed set (TRANSPORT_SOURCE_* in mod/profile.py). Kept as a Literal on
# the message so it stays a faithful wire echo; the device-side canonical
# form is modalapi.sync.SyncMode (parse via SyncMode.parse).
SyncModeWire = Literal["Internal", "link", "midi_clock_slave"]


@dataclass
class LoadingStartMessage:
    """Pedalboard loading started."""

    is_default: bool


@dataclass
class LoadingEndMessage:
    """Pedalboard loading finished."""

    snapshot_id: int


@dataclass
class PedalSnapshotMessage:
    """Snapshot changed within current pedalboard."""

    snapshot_id: int
    snapshot_name: str


@dataclass
class SizeMessage:
    """Pedalboard canvas size."""

    width: int
    height: int


@dataclass
class AddHwPortMessage:
    """Hardware port appeared (JACK)."""

    port_name: str
    port_type: str  # "audio" or "midi"
    is_output: bool
    title: str
    index: int


@dataclass
class RemoveHwPortMessage:
    """Hardware port disappeared."""

    port_name: str


@dataclass
class TrueBypassMessage:
    """True bypass state changed."""

    left: int
    right: int


@dataclass
class PluginBypassMessage:
    """Plugin bypass state changed (received as param_set ... :bypass ...)."""

    instance: str  # canonical bare form, e.g. "CollisionDrive"
    bypassed: bool


@dataclass
class TransportMessage:
    """Transport state changed (transport {rolling} {beatsPerBar} {bpm} {syncMode}).

    syncMode is mod-ui's label for the clock source. We keep the raw wire
    token (see ``SyncModeWire``) so the message stays a faithful echo; the
    consumer normalizes via ``modalapi.sync.SyncMode.parse`` (see
    ableton-link.md §6.1)."""

    rolling: bool
    bpm: float
    sync_mode: SyncModeWire = "Internal"


@dataclass
class AddPluginMessage:
    """Plugin present in a (re)connect/load dump, or dynamically added (add ...)."""

    instance: str  # canonical bare form, e.g. "CollisionDrive"
    uri: str       # LV2 plugin URI
    x: float       # mod-ui canvas X
    y: float       # mod-ui canvas Y
    bypassed: bool


@dataclass
class PatchSetMessage:
    """A plugin's writable property changed (`patch_set ...`). Replayed in full
    on the connect dump, so it also carries state for boards loaded before we
    connected."""

    instance: str    # canonical bare form, e.g. "notes"
    param_uri: str   # LV2 property URI
    value_type: str  # mod-host type char: s(tring) p(ath) i(nt) f(loat) ...
    value: str       # raw; paths may contain spaces


@dataclass
class RemovePluginMessage:
    """Plugin dynamically removed from the active pedalboard (remove ...)."""

    instance: str  # canonical bare form, e.g. "CollisionDrive"


@dataclass
class ConnectMessage:
    """Two ports connected in the active pedalboard (connect ...)."""

    port_from: str  # e.g. "/graph/PluginA/out_L"
    port_to: str    # e.g. "/graph/PluginB/in_L"


@dataclass
class DisconnectMessage:
    """Two ports disconnected in the active pedalboard (disconnect ...)."""

    port_from: str
    port_to: str


@dataclass
class ParamSetMessage:
    """A plugin control-port value changed (param_set, non-:bypass)."""

    instance: str  # canonical bare form, e.g. "HotBox"
    symbol: Symbol  # e.g. Symbol("gain")
    value: float


@dataclass
class MidiMapMessage:
    """A MIDI binding was learned/assigned in mod-ui (midi_map ...)."""

    instance: str  # canonical bare form, e.g. "CollisionDrive"
    symbol: Symbol  # e.g. Symbol("gain") or BYPASS_SYMBOL
    channel: int
    controller: int

    @property
    def binding(self) -> str:
        # Matches Parameter.binding's "channel:controller" form.
        return "%d:%d" % (self.channel, self.controller)


@dataclass
class UnknownMessage:
    """Message type we don't handle yet."""

    raw: str


# Union of all message types
WebSocketMessage = Union[
    LoadingStartMessage,
    LoadingEndMessage,
    PedalSnapshotMessage,
    SizeMessage,
    AddHwPortMessage,
    RemoveHwPortMessage,
    TrueBypassMessage,
    PluginBypassMessage,
    TransportMessage,
    AddPluginMessage,
    PatchSetMessage,
    RemovePluginMessage,
    ConnectMessage,
    DisconnectMessage,
    ParamSetMessage,
    MidiMapMessage,
    UnknownMessage,
]


def parse_message(raw_message: str) -> WebSocketMessage:
    """Parse raw WebSocket message string into typed message object."""
    try:
        match raw_message.split(" ", 2):
            # Format: loading_start {isDefault}
            case ["loading_start", flag, *_]:
                return LoadingStartMessage(is_default=bool(int(flag)))
            case ["loading_start", *_]:
                return LoadingStartMessage(is_default=False)

            # Format: loading_end {snapshotId}
            case ["loading_end", sid, *_]:
                return LoadingEndMessage(snapshot_id=int(sid))
            case ["loading_end"]:
                return LoadingEndMessage(snapshot_id=0)

            # Format: pedal_snapshot {snapshotId} {snapshotName}
            case ["pedal_snapshot", sid, name]:
                return PedalSnapshotMessage(snapshot_id=int(sid), snapshot_name=name)
            case ["pedal_snapshot", sid]:
                return PedalSnapshotMessage(snapshot_id=int(sid), snapshot_name="")
            case ["pedal_snapshot"]:
                return PedalSnapshotMessage(snapshot_id=0, snapshot_name="")

            # Format: size {width} {height}
            case ["size", w, h_trailing]:
                return SizeMessage(width=int(w), height=int(h_trailing.split()[0]))
            case ["size", w]:
                return SizeMessage(width=int(w), height=0)
            case ["size"]:
                return SizeMessage(width=0, height=0)

            # Format: add_hw_port /graph/{name} {type} {isOutput} {title} {index}
            case ["add_hw_port", port_name, rest]:
                match rest.split(" ", 3):
                    case [port_type, is_out, title, index]:
                        return AddHwPortMessage(
                            port_name=port_name,
                            port_type=port_type,
                            is_output=bool(int(is_out)),
                            title=title,
                            index=int(index),
                        )
                    case [port_type, is_out, title]:
                        return AddHwPortMessage(
                            port_name=port_name, port_type=port_type, is_output=bool(int(is_out)), title=title, index=0
                        )
                    case [port_type, is_out]:
                        return AddHwPortMessage(
                            port_name=port_name, port_type=port_type, is_output=bool(int(is_out)), title="", index=0
                        )
                    case [port_type]:
                        return AddHwPortMessage(
                            port_name=port_name, port_type=port_type, is_output=False, title="", index=0
                        )
            case ["add_hw_port", port_name]:
                return AddHwPortMessage(port_name=port_name, port_type="", is_output=False, title="", index=0)

            # Format: add {instance} {uri} {x} {y} {bypassed} {sversion} {buildEnv}
            case ["add", instance_path, rest]:
                parts = rest.split()
                return AddPluginMessage(
                    instance=instance_path.removeprefix("/graph/"),
                    uri=parts[0],
                    x=float(parts[1]),
                    y=float(parts[2]),
                    bypassed=int(parts[3]) != 0,
                )

            # Format: patch_set {instance} {writable} {paramUri} {valueType} {value}
            case ["patch_set", instance_path, rest]:
                parts = rest.split(" ", 3)
                if len(parts) < 4:
                    return UnknownMessage(raw=raw_message)
                return PatchSetMessage(
                    instance=instance_path.removeprefix("/graph/"),
                    param_uri=parts[1],
                    value_type=parts[2],
                    value=parts[3],
                )

            # Format: remove {instance}
            case ["remove", instance_path]:
                return RemovePluginMessage(instance=instance_path.removeprefix("/graph/"))

            # Format: connect {port_from} {port_to}
            case ["connect", port_from, port_to]:
                return ConnectMessage(port_from=port_from, port_to=port_to)

            # Format: disconnect {port_from} {port_to}
            case ["disconnect", port_from, port_to]:
                return DisconnectMessage(port_from=port_from, port_to=port_to)

            # Format: remove_hw_port /graph/{name}
            case ["remove_hw_port", port_name, *_]:
                return RemoveHwPortMessage(port_name=port_name)
            case ["remove_hw_port"]:
                return RemoveHwPortMessage(port_name="")

            # Format: param_set /graph/{instance} :bypass {value}
            case ["param_set", path, rest] if rest.startswith(":bypass "):
                instance = path.removeprefix("/graph/")
                value_str = rest.split(" ", 1)[1]
                return PluginBypassMessage(instance=instance, bypassed=float(value_str) != 0.0)

            # Format: param_set /graph/{instance} {symbol} {value}  (must follow :bypass arm)
            case ["param_set", path, rest]:
                instance = path.removeprefix("/graph/")
                symbol, value_str = rest.split(" ", 1)
                return ParamSetMessage(instance=instance, symbol=Symbol(symbol), value=float(value_str))

            # Format: midi_map /graph/{instance} {symbol} {channel} {controller} {min} {max}
            case ["midi_map", path, rest]:
                symbol, ch, ctrl = rest.split(" ")[:3]
                return MidiMapMessage(
                    instance=path.removeprefix("/graph/"),
                    symbol=Symbol(symbol),
                    channel=int(ch),
                    controller=int(ctrl),
                )

            # Format: truebypass {left} {right}
            case ["truebypass", left, right_trailing]:
                return TrueBypassMessage(left=int(left), right=int(right_trailing.split()[0]))
            case ["truebypass", left]:
                return TrueBypassMessage(left=int(left), right=0)
            case ["truebypass"]:
                return TrueBypassMessage(left=0, right=0)

            # Format: transport {rolling} {beatsPerBar} {bpm} {syncMode}
            case ["transport", rolling, rest]:
                parts = rest.split()
                bpm = float(parts[1])
                # mod-ui broadcasts the syncMode token on every transport message
                # (and on new WebSocket connect); older installs may omit it.
                sync_mode = parts[2] if len(parts) > 2 else "Internal"
                return TransportMessage(rolling=rolling != "0", bpm=bpm, sync_mode=cast(SyncModeWire, sync_mode))

    except (ValueError, IndexError) as e:
        logging.warning(f"Failed to parse WebSocket message '{raw_message}': {e}")
        return UnknownMessage(raw=raw_message)

    return UnknownMessage(raw=raw_message)
