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
from typing import Callable, Optional

from . import ops
from .commands import CommandQueue
from .nmcli import nmcli, parse_kv_lines
from .types import SavedConnection, ScannedNetwork, WifiStatus


class WifiManager:
    # Hard-wired wifi interface to avoid scrubbing sysfs.
    # Hotspot state is read from / mutates via NetworkManager directly.
    def __init__(self, ifname: str = "wlan0", on_status_change: Optional[Callable[[WifiStatus], None]] = None) -> None:
        self.iface_name: str = ifname
        self.lock: threading.Lock = threading.Lock()
        self.last_status: WifiStatus = {}
        self._cached_saved: list[SavedConnection] = []
        self.changed: bool = False
        self.on_status_change: Optional[Callable[[WifiStatus], None]] = on_status_change
        self.stop: threading.Event = threading.Event()
        self.wireless_supported: bool = False
        self.wireless_file: str = os.path.join(os.sep, "sys", "class", "net", self.iface_name, "wireless")
        self.operstate_file: str = os.path.join(os.sep, "sys", "class", "net", self.iface_name, "operstate")
        self.queue: CommandQueue = CommandQueue(self)
        self.thread = threading.Thread(target=self._polling_thread, daemon=True)
        self.thread.start()

    def __del__(self) -> None:
        logging.info("Wifi monitor cleanup")
        self.shutdown()

    def shutdown(self) -> None:
        self.stop.set()
        try:
            self.queue.shutdown()
        except Exception:
            pass
        if self.thread is not None:
            self.thread.join(timeout=2.0)

    def _is_wifi_supported(self) -> bool:
        if self.wireless_supported:
            return True
        self.wireless_supported = os.path.exists(self.wireless_file)
        return self.wireless_supported

    def _is_wifi_connected(self) -> bool:
        try:
            with open(self.operstate_file) as f:
                return f.readline().startswith("up")
        except Exception:
            return False

    def _get_wpa_status(self, status: WifiStatus) -> None:
        # `device show` rejects per-setting fields; fetch SSID/mode via `connection show` below.
        stdout, err = nmcli(
            ["device", "show", self.iface_name],
            terse_fields=["GENERAL.STATE", "GENERAL.CONNECTION", "IP4.ADDRESS"],
            timeout=10,
        )
        if err is not None or stdout is None:
            logging.error("nmcli device show failed: " + (err or b"").decode("utf-8", "replace"))
            return
        kv = parse_kv_lines(stdout)
        if "GENERAL.STATE" in kv:
            status["state"] = kv["GENERAL.STATE"]
        if "GENERAL.CONNECTION" in kv:
            status["connection"] = kv["GENERAL.CONNECTION"]
        for key, value in kv.items():
            if key == "IP4.ADDRESS" or key.startswith("IP4.ADDRESS["):
                status["ip4_address"] = value
                break
        connection = status.get("connection")
        if connection:
            ssid, mode = ops.wifi_profile_ssid_mode(connection)
            if ssid:
                status["ssid"] = ssid
            status["hotspot_active"] = mode == "ap"

    def _polling_thread(self) -> None:
        while True:
            new_status: WifiStatus = {}
            supported = new_status["wifi_supported"] = self._is_wifi_supported()
            connected = new_status["wifi_connected"] = self._is_wifi_connected()
            # Default false; _get_wpa_status flips it when the active wlan0
            # connection has mode=ap. operstate is "up" in both client and AP
            # modes, so `connected` covers both cases.
            new_status["hotspot_active"] = False
            if supported and connected:
                self._get_wpa_status(new_status)

            saved = ops.list_connections() if supported else []

            with self.lock:
                self._cached_saved = saved
                if new_status != self.last_status:
                    logging.debug("Wifi status changed:" + str(new_status))
                    self.last_status = new_status
                    self.changed = True

            if self.stop.wait(5.0):
                break

    def poll(self) -> None:
        """Main-thread tick. Drains write-op callbacks and fires
        on_status_change when the polling thread has new status."""
        self.queue.poll()
        update: Optional[WifiStatus] = None
        with self.lock:
            if self.changed:
                update = self.last_status
                self.changed = False
        if update is not None and self.on_status_change is not None:
            self.on_status_change(update)

    def get_cached_saved(self) -> list[SavedConnection]:
        with self.lock:
            return list(self._cached_saved)

    def list_connections(self) -> list[SavedConnection]:
        return ops.list_connections()

    def scan_networks(self) -> list[ScannedNetwork]:
        return ops.scan_networks(self.iface_name)

    def connect_scanned(self, ssid: str, security: str, psk: Optional[str] = None) -> Optional[bytes]:
        return ops.connect_scanned(self.iface_name, ssid, security, psk)

    def connect_saved(self, name: str, wait: bool = True, reconnect: bool = False) -> Optional[bytes]:
        return ops.connect_saved(name, wait=wait, reconnect=reconnect)

    def disconnect(self, name: str) -> Optional[bytes]:
        return ops.disconnect(name)

    def delete_connection(self, name: str) -> Optional[bytes]:
        return ops.delete_connection(name)

    def replace_psk(self, name: str, psk: str) -> Optional[bytes]:
        return ops.replace_psk(name, psk)

    def get_psk_for(self, name: str) -> Optional[str]:
        return ops.get_psk_for(name)

    def enable_hotspot(self) -> Optional[bytes]:
        return ops.enable_hotspot(self.iface_name)

    def disable_hotspot(self) -> Optional[bytes]:
        return ops.disable_hotspot(self.iface_name)
