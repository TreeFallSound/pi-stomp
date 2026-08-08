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

import logging
import os
import threading
import time
from typing import Callable, Optional, Protocol

from common.command_queue import CommandQueue

from . import ops
from .bluez import BluezClient
from .types import BtDevice, BtStatus, DeviceKind, KnownDevice

SETTING_KEY = "bluetooth.known_devices"
HCI_SYSFS_DIR = os.path.join(os.sep, "sys", "class", "bluetooth")


def has_adapter(sysfs_dir: str = HCI_SYSFS_DIR) -> bool:
    try:
        return any(name.startswith("hci") for name in os.listdir(sysfs_dir))
    except OSError:
        return False


class SettingsStore(Protocol):
    """The slice of pistomp.settings.Settings the known-device store needs."""

    def get_setting(self, name: str) -> object: ...
    def set_setting(self, name: str, value: object) -> None: ...


class BluetoothManager:
    """Owns the bluez client, the known-device store, and a CommandQueue.

    Unlike wifi there is no periodic status poll: bluez pushes
    PropertiesChanged, so `changed` is set from the client's callback and
    drained by poll() on the main thread."""

    def __init__(
        self,
        settings: Optional[SettingsStore] = None,
        on_status_change: Optional[Callable[[BtStatus], None]] = None,
    ) -> None:
        self.lock: threading.Lock = threading.Lock()
        self.settings: Optional[SettingsStore] = settings
        self.on_status_change: Optional[Callable[[BtStatus], None]] = on_status_change
        self.client: BluezClient = BluezClient()
        self.last_status: BtStatus = {}
        self._last_sig: tuple = ()
        self.changed: bool = False
        self._has_adapter: bool = has_adapter()
        self._capable: bool = False
        self._enabled: bool = False
        self._probed: bool = False
        self.queue: CommandQueue = CommandQueue(self)
        self._start_thread = threading.Thread(target=self._startup, name="bt-start", daemon=True)
        self._start_thread.start()

    # ----- startup / status -----

    def _startup(self) -> None:
        """Probe the image's capability and connect to bluez. Both block, so
        neither may run on the UI thread."""
        if not self._has_adapter:
            self._probed = True
            return
        self._capable = ops.bluetoothd_is_capable()
        self._enabled = ops.service_enabled()
        if self._enabled and self.client.start(on_change=self.request_refresh):
            self.client.call(ops.power_on(self.client))
        self._probed = True
        self.request_refresh()

    def request_refresh(self) -> None:
        with self.lock:
            self.changed = True

    @property
    def supported(self) -> bool:
        """Hardware present. Pi 3/4 hand the BT UART to DIN MIDI via
        dtoverlay=pi3-disable-bt, so no hci device is registered and no row is
        ever shown. The node exists whether or not bluetoothd is running, which
        is what lets the menu offer to turn Bluetooth on."""
        return self._has_adapter

    @property
    def capable(self) -> bool:
        return self._capable

    def status(self) -> BtStatus:
        devices = self.client.snapshot() if self.client.available else []
        return BtStatus(
            supported=self.supported,
            capable=self._capable,
            enabled=self._enabled,
            powered=self.client.powered,
            discovering=self.client.discovering,
            connected=[d["name"] for d in devices if d["connected"]],
        )

    def poll(self) -> None:
        """Main-thread tick: drain callbacks, publish a changed snapshot."""
        self.queue.poll()
        publish = False
        with self.lock:
            if self.changed:
                self.changed = False
                publish = True
        if not publish:
            return
        status = self.status()
        # Devices are not part of the published status, so the status alone
        # cannot tell a new discovery from a repeat — dedupe on both.
        sig = (tuple(sorted(status.items())), self._device_sig())
        with self.lock:
            if sig == self._last_sig:
                return
            self._last_sig = sig
            self.last_status = status
        if self.on_status_change is not None:
            self.on_status_change(status)

    def _device_sig(self) -> tuple:
        """RSSI bucketed to the drawn bar count so jitter doesn't republish."""
        return tuple(
            sorted(
                (d["address"], d["name"], d["paired"], d["connected"], None if d["rssi"] is None else d["rssi"] // 10)
                for d in self.devices()
            )
        )

    def shutdown(self) -> None:
        try:
            self.queue.shutdown()
        except Exception:
            pass
        self.client.stop()

    # ----- devices -----

    def devices(self) -> list[BtDevice]:
        return self.client.snapshot() if self.client.available else []

    def known_devices(self) -> list[KnownDevice]:
        if self.settings is None:
            return []
        raw = self.settings.get_setting(SETTING_KEY)
        if not isinstance(raw, list):
            return []
        out: list[KnownDevice] = []
        for item in raw:
            if not isinstance(item, dict) or not item.get("address"):
                continue
            out.append(
                KnownDevice(
                    address=str(item.get("address") or ""),
                    name=str(item.get("name") or ""),
                    kind=str(item.get("kind") or DeviceKind.OTHER.value),
                    last_connected=int(item.get("last_connected") or 0),
                )
            )
        return out

    def remember(self, device: BtDevice) -> None:
        """Record a successful pairing. Keyed on address *and* name: BLE
        resolvable private addresses re-randomise, so a new address under a
        known name is the same device, not a second one."""
        if self.settings is None:
            return
        entry = KnownDevice(
            address=device["address"],
            name=device["name"],
            kind=device["kind"].value,
            last_connected=int(time.time()),
        )
        kept = [
            k
            for k in self.known_devices()
            if k["address"].upper() != entry["address"].upper() and not (k["name"] and k["name"] == entry["name"])
        ]
        self.settings.set_setting(SETTING_KEY, list(kept) + [entry])

    def forget(self, address: str, name: str) -> None:
        if self.settings is None:
            return
        kept = [
            k
            for k in self.known_devices()
            if k["address"].upper() != address.upper() and not (name and k["name"] == name)
        ]
        self.settings.set_setting(SETTING_KEY, kept)

    # ----- verbs, called from the queue's worker thread -----

    def set_enabled(self, enabled: bool) -> Optional[str]:
        err = ops.enable_service() if enabled else ops.disable_service()
        if err is not None:
            return err
        self._enabled = enabled
        if enabled:
            self.client.start(on_change=self.request_refresh)
            if self.client.available:
                self.client.call(ops.power_on(self.client))
        self.request_refresh()
        return None

    def install_support(self) -> Optional[str]:
        err = ops.install_support_package()
        if err is None:
            self._capable = ops.bluetoothd_is_capable()
            self.request_refresh()
        return err

    def start_discovery(self) -> None:
        if self.client.available:
            self.client.call(ops.start_discovery(self.client))

    def stop_discovery(self) -> None:
        if self.client.available:
            self.client.call(ops.stop_discovery(self.client))

    def resolve_path(self, device: BtDevice) -> Optional[str]:
        """A stored path can be stale — bluez purges unpaired LE objects the
        moment discovery stops. Fall back to a fresh address lookup."""
        if self.client.device_props(device["path"]):
            return device["path"]
        return self.client.find_path(device["address"])

    def pair(self, device: BtDevice) -> None:
        path = self.resolve_path(device)
        if path is None:
            raise RuntimeError("the device is no longer in range")
        ops.pair_and_connect(self.client, path)
        self.remember(device)

    def connect(self, device: BtDevice) -> None:
        path = self.resolve_path(device)
        if path is None:
            raise RuntimeError("the device is no longer in range")
        ops.connect(self.client, path)
        self.remember(device)

    def disconnect(self, device: BtDevice) -> None:
        path = self.resolve_path(device)
        if path is not None:
            ops.disconnect(self.client, path)

    def remove(self, device: BtDevice) -> None:
        path = self.resolve_path(device)
        if path is not None:
            try:
                ops.remove(self.client, path)
            except Exception:
                logging.exception("RemoveDevice failed for %s", device["address"])
        self.forget(device["address"], device["name"])
