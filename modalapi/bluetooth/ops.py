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

"""Stateless bluetooth verbs. Every function here blocks and must run on the
CommandQueue worker thread, never the UI thread."""

import asyncio
import logging
import subprocess
import time
from typing import Optional

from dbus_fast import DBusError, Variant

from .bluez import BluezClient

SUPPORT_PACKAGE = "pistomp-bluetooth"
SERVICE = "bluetooth.service"

_PAIR_TIMEOUT_S = 45.0
_CONNECT_TIMEOUT_S = 30.0
_POLL_INTERVAL_S = 0.25
_BUSY_RETRIES = 16
_BUSY_RETRY_INTERVAL_S = 0.25


def _run(args: list[str], timeout: int = 30, sudo: bool = False) -> tuple[int, str]:
    # pi-Stomp runs as the `pistomp` user; anything that mutates system state
    # needs sudo, as the wifi module's nmcli calls already do.
    cmd = (["sudo", "-n"] if sudo else []) + args
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return 1, str(e)
    out = (p.stdout or b"").decode("utf-8", "replace") + (p.stderr or b"").decode("utf-8", "replace")
    return p.returncode, out.strip()


# ----- image capability -----


def bluetoothd_is_capable() -> bool:
    """True when bluetoothd will start with -E, which is what registers the
    BLE-MIDI GATT profile. systemd reports the merged unit config even while
    the service is disabled, so this answers from a cold start."""
    rc, out = _run(["systemctl", "show", SERVICE, "-p", "ExecStart", "--value"], timeout=10)
    if rc != 0:
        return False
    return has_experimental_flag(out)


def has_experimental_flag(exec_start: str) -> bool:
    """Scan a systemd ExecStart value for bluetoothd's experimental flag."""
    for token in exec_start.replace(";", " ").split():
        if token == "--experimental":
            return True
        # Short flags may be clustered ("-nE"); long options must not match.
        if token.startswith("-") and not token.startswith("--") and "E" in token[1:]:
            return True
    return False


def service_enabled() -> bool:
    rc, out = _run(["systemctl", "is-enabled", SERVICE], timeout=10)
    return rc == 0 and out.startswith("enabled")


def enable_service() -> Optional[str]:
    rc, out = _run(["systemctl", "enable", "--now", SERVICE], timeout=60, sudo=True)
    return None if rc == 0 else out


def disable_service() -> Optional[str]:
    rc, out = _run(["systemctl", "disable", "--now", SERVICE], timeout=60, sudo=True)
    return None if rc == 0 else out


def install_support_package() -> Optional[str]:
    """Fetch pistomp-bluetooth from the pistomp apt repo. Needs a network."""
    rc, out = _run(["apt-get", "update"], timeout=180, sudo=True)
    if rc != 0:
        logging.warning("apt-get update failed: %s", out)
    rc, out = _run(["apt-get", "install", "-y", SUPPORT_PACKAGE], timeout=300, sudo=True)
    return None if rc == 0 else out


def rfkill_set_blocked(blocked: bool) -> Optional[str]:
    """Mirror of pistomp-bluetooth's drop-in soft-unblock, both directions, so
    "off" means off even if bluetoothd exited without powering down. Writes
    sysfs because the image ships no rfkill(8); trailing `true` tolerates a
    board with no bluetooth rfkill node."""
    script = 'for f in /sys/class/rfkill/*; do [ "$(cat $f/type)" = bluetooth ] && echo %d > $f/soft; done; true' % (
        1 if blocked else 0
    )
    rc, out = _run(["sh", "-c", script], timeout=10, sudo=True)
    return None if rc == 0 else out


# ----- adapter -----


async def _set_adapter_flag(client: BluezClient, name: str, value: bool = True) -> None:
    """A freshly restarted bluetoothd answers Busy until the adapter finishes
    initialising. That resolves on its own, so retry a bounded number of times
    rather than putting a dialog in front of the user."""
    for attempt in range(_BUSY_RETRIES + 1):
        try:
            await client.set_adapter_property(name, Variant("b", value))
            return
        except DBusError as e:
            if "Busy" not in str(e) or attempt == _BUSY_RETRIES:
                raise
            await asyncio.sleep(_BUSY_RETRY_INTERVAL_S)


async def power_on(client: BluezClient) -> None:
    await _set_adapter_flag(client, "Powered")
    # Pairable persists in the adapter's settings, but say it explicitly rather
    # than inherit whatever a previous session left behind.
    await _set_adapter_flag(client, "Pairable")


async def power_off(client: BluezClient) -> None:
    """Take the radio down. Must run while bluetoothd is still alive: the
    adapter's D-Bus object disappears with the daemon. Discoverable and
    Pairable go first so nothing can pair in the gap; neither is fatal."""
    for name in ("Discoverable", "Pairable"):
        try:
            await _set_adapter_flag(client, name, False)
        except DBusError as e:
            logging.warning("Bluetooth: clearing %s failed: %s", name, e)
    await _set_adapter_flag(client, "Powered", False)


async def start_discovery(client: BluezClient) -> None:
    if client.discovering:
        return
    await client.adapter_call(
        "SetDiscoveryFilter",
        "a{sv}",
        [{"Transport": Variant("s", "auto"), "DuplicateData": Variant("b", False)}],
    )
    try:
        await client.adapter_call("StartDiscovery")
    except DBusError as e:
        if "InProgress" not in str(e):
            raise


async def stop_discovery(client: BluezClient) -> None:
    if not client.discovering:
        return
    try:
        await client.adapter_call("StopDiscovery")
    except DBusError as e:
        logging.debug("StopDiscovery: %s", e)


# ----- devices -----


def _wait_for_flag(client: BluezClient, path: str, flag: str, timeout: float) -> bool:
    """Poll the signal-fed device dict until `flag` goes true. Used to ride out
    org.bluez.Error.InProgress, which means an attempt is already running."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        props = client.device_props(path)
        if not props:
            return False  # bluez purged the object — the device went away
        if props.get(flag):
            return True
        time.sleep(_POLL_INTERVAL_S)
    return False


async def _pair(client: BluezClient, path: str) -> None:
    await client.device_call(path, "Pair")


def pair_and_connect(client: BluezClient, path: str) -> None:
    """Pair, then trust, then connect — in that order.

    Trusting first makes bluez auto-connect the moment the device is seen, and
    that in-flight attempt makes our own Pair() return InProgress. Only a
    fresh, untrusted device pairs reliably."""
    props = client.device_props(path)
    if not props:
        raise RuntimeError("the device is no longer in range")

    if not props.get("Paired"):
        try:
            client.call(_pair(client, path), timeout=_PAIR_TIMEOUT_S)
        except DBusError as e:
            text = str(e)
            if "AlreadyExists" in text:
                pass
            elif "InProgress" in text:
                if not _wait_for_flag(client, path, "Paired", _PAIR_TIMEOUT_S):
                    raise
            else:
                raise

    # Trust is what lets bluez auto-accept this device's future reconnections;
    # ReconnectUUIDs doesn't cover MIDI.
    try:
        client.call(client.set_device_property(path, "Trusted", Variant("b", True)))
    except DBusError as e:
        logging.warning("Couldn't trust %s: %s", path, e)

    connect(client, path)


def connect(client: BluezClient, path: str) -> None:
    if client.device_props(path).get("Connected"):
        return
    try:
        client.call(client.device_call(path, "Connect"), timeout=_CONNECT_TIMEOUT_S)
    except DBusError as e:
        if "InProgress" not in str(e):
            raise
        if not _wait_for_flag(client, path, "Connected", _CONNECT_TIMEOUT_S):
            raise


def disconnect(client: BluezClient, path: str) -> None:
    client.call(client.device_call(path, "Disconnect"), timeout=_CONNECT_TIMEOUT_S)


def remove(client: BluezClient, path: str) -> None:
    try:
        client.call(client.adapter_call("RemoveDevice", "o", [path]))
    except DBusError as e:
        if "DoesNotExist" not in str(e):
            raise
