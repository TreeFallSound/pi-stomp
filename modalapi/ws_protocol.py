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
    """
    Parse raw WebSocket message string into typed message object.

    Args:
        raw_message: Raw message string from WebSocket

    Returns:
        Typed message object
    """
    parts = raw_message.split(' ', 2)
    if not parts:
        return UnknownMessage(raw=raw_message)

    cmd = parts[0]

    try:
        if cmd == "loading_start":
            is_default = bool(int(parts[1])) if len(parts) > 1 else False
            return LoadingStartMessage(is_default=is_default)

        elif cmd == "loading_end":
            snapshot_id = int(parts[1]) if len(parts) > 1 else 0
            return LoadingEndMessage(snapshot_id=snapshot_id)

        elif cmd == "pedal_snapshot":
            snapshot_id = int(parts[1]) if len(parts) > 1 else 0
            snapshot_name = parts[2] if len(parts) > 2 else ""
            return PedalSnapshotMessage(snapshot_id=snapshot_id, snapshot_name=snapshot_name)

        elif cmd == "size":
            width = int(parts[1]) if len(parts) > 1 else 0
            height = int(parts[2].split()[0]) if len(parts) > 2 else 0
            return SizeMessage(width=width, height=height)

        elif cmd == "add_hw_port":
            # Format: add_hw_port /graph/{name} {type} {isOutput} {title} {index}
            if len(parts) > 1:
                details = parts[1].split(' ', 4)
                port_name = details[0] if len(details) > 0 else ""
                port_type = details[1] if len(details) > 1 else ""
                is_output = bool(int(details[2])) if len(details) > 2 else False
                title = details[3] if len(details) > 3 else ""
                index = int(details[4]) if len(details) > 4 else 0
                return AddHwPortMessage(
                    port_name=port_name,
                    port_type=port_type,
                    is_output=is_output,
                    title=title,
                    index=index
                )

        elif cmd == "remove_hw_port":
            port_name = parts[1] if len(parts) > 1 else ""
            return RemoveHwPortMessage(port_name=port_name)

        elif cmd == "truebypass":
            left = int(parts[1]) if len(parts) > 1 else 0
            right = int(parts[2].split()[0]) if len(parts) > 2 else 0
            return TrueBypassMessage(left=left, right=right)

    except (ValueError, IndexError) as e:
        logging.warning(f"Failed to parse WebSocket message '{raw_message}': {e}")
        return UnknownMessage(raw=raw_message)

    # Unknown command
    return UnknownMessage(raw=raw_message)
