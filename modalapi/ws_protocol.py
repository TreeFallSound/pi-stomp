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
from typing import Union
import logging


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

            # Format: remove_hw_port /graph/{name}
            case ["remove_hw_port", port_name, *_]:
                return RemoveHwPortMessage(port_name=port_name)
            case ["remove_hw_port"]:
                return RemoveHwPortMessage(port_name="")

            # Format: truebypass {left} {right}
            case ["truebypass", left, right_trailing]:
                return TrueBypassMessage(left=int(left), right=int(right_trailing.split()[0]))
            case ["truebypass", left]:
                return TrueBypassMessage(left=int(left), right=0)
            case ["truebypass"]:
                return TrueBypassMessage(left=0, right=0)

    except (ValueError, IndexError) as e:
        logging.warning(f"Failed to parse WebSocket message '{raw_message}': {e}")
        return UnknownMessage(raw=raw_message)

    return UnknownMessage(raw=raw_message)
