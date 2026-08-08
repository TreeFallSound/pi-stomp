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

from enum import Enum
from typing import Any, Optional, TypedDict

BLUEZ_SERVICE = "org.bluez"
ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICE_IFACE = "org.bluez.Device1"
AGENT_MANAGER_IFACE = "org.bluez.AgentManager1"
AGENT_IFACE = "org.bluez.Agent1"
AGENT_PATH = "/org/pistomp/bt_agent"

MIDI_UUID = "03b80e5a-ede8-4b33-a751-6ce34ec4c700"
HOG_UUID = "00001812-0000-1000-8000-00805f9b34fb"  # HID over GATT
HID_UUID = "00001124-0000-1000-8000-00805f9b34fb"  # BR/EDR HID
PERIPHERAL_MAJOR_CLASS = 0x05
APPEARANCE_HID_RANGE = range(0x03C0, 0x03C5)


class DeviceKind(str, Enum):
    MIDI = "midi"
    INPUT = "input"
    OTHER = "other"


class BtDevice(TypedDict):
    path: str  # D-Bus object path — the handle Pair/Connect are issued against
    address: str
    name: str  # Device1.Name; "" when the device advertises none
    kind: DeviceKind
    paired: bool
    connected: bool
    trusted: bool
    rssi: Optional[int]


class KnownDevice(TypedDict):
    """Our own record of a device the user has paired at least once. Survives
    bluez forgetting a non-bonding device the moment it disconnects."""

    address: str
    name: str
    kind: str
    last_connected: int


class BtStatus(TypedDict, total=False):
    supported: bool  # an adapter exists on this board
    capable: bool  # bluetoothd is running with -E, so the MIDI profile registers
    enabled: bool  # bluetooth.service is enabled
    powered: bool
    discovering: bool
    connected: list[str]  # names of currently connected devices


def _uuids(props: dict[str, Any]) -> set[str]:
    raw = props.get("UUIDs") or []
    return {str(u).lower() for u in raw}


def device_kind(props: dict[str, Any]) -> DeviceKind:
    """Classify a Device1 property dict. MIDI wins over INPUT — a device that
    is both is here to make music."""
    uuids = _uuids(props)
    if MIDI_UUID in uuids:
        return DeviceKind.MIDI
    if HOG_UUID in uuids or HID_UUID in uuids:
        return DeviceKind.INPUT
    cls = props.get("Class")
    if isinstance(cls, int) and (cls >> 8) & 0x1F == PERIPHERAL_MAJOR_CLASS:
        return DeviceKind.INPUT
    appearance = props.get("Appearance")
    if isinstance(appearance, int) and appearance in APPEARANCE_HID_RANGE:
        return DeviceKind.INPUT
    return DeviceKind.OTHER


def is_interesting(props: dict[str, Any]) -> bool:
    """True for devices worth listing: anything already paired, or a *named*
    MIDI/HID device.

    Tests Name, never Alias. BlueZ fills Alias with a MAC-derived string for
    nameless devices, so Alias is always truthy and would admit every beacon
    in the room; absent Name is the only discriminator."""
    if props.get("Paired"):
        return True
    if not props.get("Name"):
        return False
    return device_kind(props) is not DeviceKind.OTHER


_ERRORS = {
    "org.bluez.Error.AuthenticationFailed": "pairing failed",
    "org.bluez.Error.AuthenticationRejected": "the device rejected pairing",
    "org.bluez.Error.AuthenticationCanceled": "pairing was cancelled",
    "org.bluez.Error.AuthenticationTimeout": "the device stopped responding",
    "org.bluez.Error.ConnectionAttemptFailed": "couldn't connect — is it still in pairing mode?",
    "org.bluez.Error.NotReady": "the Bluetooth adapter isn't ready",
    "org.bluez.Error.NotAvailable": "the device is no longer in range",
    "org.bluez.Error.DoesNotExist": "the device is no longer in range",
    "org.bluez.Error.NotSupported": "this device isn't supported",
    "org.bluez.Error.InProgress": "already connecting",
    "org.bluez.Error.NotPermitted": "not permitted",
    "org.bluez.Error.NotAuthorized": "not authorized",
}


def parse_bluez_error(err: object) -> str:
    """Map a D-Bus error (or any exception) to a short user-facing reason."""
    if err is None:
        return "unknown error"
    text = str(err)
    for name, message in _ERRORS.items():
        if name in text:
            return message
    lower = text.lower()
    if "not available" in lower or "unknownobject" in lower or "no such" in lower:
        return "the device is no longer in range"
    if "in progress" in lower or "inprogress" in lower:
        return "already connecting"
    if "timeout" in lower or "timed out" in lower:
        return "timed out"
    # "br-connection-page-timeout" and friends: bluez's own hint is the useful part.
    tail = text.rsplit(":", 1)[-1].strip()
    return (tail or text)[:80] or "unknown error"
