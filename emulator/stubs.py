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

"""Hardware and system stubs shared across all emulator versions.

VirtualAudiocard      — in-memory audiocard; no ALSA/hardware access.
StubWifiManager       — in-memory wifi; satisfies Mod/Modhandler's wifi_manager.
StubBluetoothManager  — in-memory bluetooth; no D-Bus, no bluez, no threads.
StubEthernetManager   — pinned-up ethernet stub; no sysfs / systemctl / threads.
StubRelay             — no-op relay; satisfies the Relay interface without GPIO.
"""

import threading
import time
from typing import Callable, Optional

from modalapi.bluetooth import BtDevice, BtStatus, DeviceKind, KnownDevice
from modalapi.bluetooth.manager import BluetoothManager
from modalapi.ethernet import EthernetManager
from modalapi.jack_mute import JackMute
from modalapi.wifi import SavedConnection, ScannedNetwork, WifiStatus
from common.command_queue import CommandQueue
from modalapi.wifi.manager import WifiManager
from pistomp.audiocard import Audiocard
import pistomp.relay


class VirtualAudiocard(Audiocard):
    """In-memory audiocard stub; holds EQ/volume/bypass state."""

    CAPTURE_VOLUME = "capture_volume"
    MASTER = "master_volume"
    DAC_EQ = "dac_eq"
    EQ_1 = "eq1"
    EQ_2 = "eq2"
    EQ_3 = "eq3"
    EQ_4 = "eq4"
    EQ_5 = "eq5"

    def __init__(self):
        self._volumes = {}
        self._switches = {}
        self._bypass_left = False
        self._bypass_right = False

    def get_sample_rate(self) -> int:
        return 48000  # no /proc/asound off-device

    def get_volume_parameter(self, param_name):
        return self._volumes.get(param_name, 0.0)

    def set_volume_parameter(self, param_name, value, store=True):
        self._volumes[param_name] = value
        return True

    def get_switch_parameter(self, param_name):
        return self._switches.get(param_name, False)

    def set_switch_parameter(self, param_name, value, store=True):
        self._switches[param_name] = value
        return True

    def get_bypass_left(self) -> bool:
        return self._bypass_left

    def set_bypass_left(self, bypass):
        self._bypass_left = bypass

    def get_bypass_right(self) -> bool:
        return self._bypass_right

    def set_bypass_right(self, bypass):
        self._bypass_right = bypass

    def set_output_muted(self, muted: bool) -> None:
        pass


class StubWifiManager(WifiManager):
    """In-memory wifi manager; exercises the full WifiManager interface
    against a fake scan list and saved-profile store.

    SSID 'BadNet' is a tripwire — connect attempts fail with a fake
    auth error so the menu's error path is reachable in the emulator."""

    HOTSPOT_PROFILE: str = "pistomp-hotspot"

    _FAKE_SCAN: list[ScannedNetwork] = [
        ScannedNetwork(ssid="HomeWifi", signal=78, security="WPA2", in_use=True),
        ScannedNetwork(ssid="GuestNet", signal=62, security="--", in_use=False),
        ScannedNetwork(ssid="CoffeeShop", signal=48, security="WPA2", in_use=False),
        ScannedNetwork(ssid="BadNet", signal=44, security="WPA2", in_use=False),
        ScannedNetwork(ssid="Neighbor", signal=28, security="WPA2", in_use=False),
    ]

    def __init__(self, on_status_change: Optional[Callable[[WifiStatus], None]] = None) -> None:
        now = int(time.time())
        self._saved: list[dict] = [
            {"name": "HomeWifi", "ssid": "HomeWifi", "psk": "hunter2hunter2", "timestamp": now},
            {"name": "CoffeeShop", "ssid": "CoffeeShop", "psk": "espresso", "timestamp": now - 86400},
        ]
        self._active: Optional[str] = "HomeWifi"
        self._hotspot_active: bool = False
        self._last_status: WifiStatus = {}
        self._changed: bool = True
        self.on_status_change: Optional[Callable[[WifiStatus], None]] = on_status_change
        self.queue: CommandQueue = CommandQueue(self)
        self._refresh_status()

    def _refresh_status(self) -> None:
        status: WifiStatus = {
            "wifi_supported": True,
            "wifi_connected": self._active is not None and not self._hotspot_active,
            "hotspot_active": self._hotspot_active,
        }
        if self._hotspot_active:
            status["state"] = "100 (connected)"
            status["connection"] = self.HOTSPOT_PROFILE
            status["ssid"] = "pi-stomp"
            status["ip4_address"] = "10.42.0.1/24"
        elif self._active is not None:
            profile = next((p for p in self._saved if p["name"] == self._active), None)
            status["state"] = "100 (connected)"
            status["connection"] = self._active
            status["ssid"] = profile["ssid"] if profile else self._active
            status["ip4_address"] = "192.168.1.42/24"
        else:
            status["state"] = "30 (disconnected)"
        if status != self._last_status:
            self._last_status = status
            self._changed = True

    def _resolve_unique_name(self, desired: str, exclude: Optional[str] = None) -> str:
        existing = {p["name"] for p in self._saved if p["name"] != exclude}
        name = desired
        counter = 2
        while name in existing:
            name = "%s (%d)" % (desired, counter)
            counter += 1
        return name

    def poll(self) -> None:
        self.queue.poll()
        if self._changed:
            self._changed = False
            if self.on_status_change is not None:
                self.on_status_change(self._last_status)

    def shutdown(self) -> None:
        try:
            self.queue.shutdown()
        except Exception:
            pass

    def get_cached_saved(self) -> list[SavedConnection]:
        return self.list_connections()

    def get_ssid(self) -> Optional[str]:
        if self._active is None:
            return None
        profile = next((p for p in self._saved if p["name"] == self._active), None)
        return profile["ssid"] if profile else None

    def get_psk(self) -> Optional[str]:
        if self._active is None:
            return None
        profile = next((p for p in self._saved if p["name"] == self._active), None)
        return profile["psk"] if profile else None

    def enable_hotspot(self) -> None:
        self._hotspot_active = True
        self._refresh_status()

    def disable_hotspot(self) -> None:
        self._hotspot_active = False
        self._refresh_status()

    def list_connections(self) -> list[SavedConnection]:
        return [SavedConnection(name=p["name"], ssid=p["ssid"], timestamp=p["timestamp"]) for p in self._saved]

    def scan_networks(self) -> list[ScannedNetwork]:
        active_ssid = self.get_ssid()
        return [
            ScannedNetwork(
                ssid=n["ssid"], signal=n["signal"], security=n["security"], in_use=(n["ssid"] == active_ssid)
            )
            for n in self._FAKE_SCAN
        ]

    def connect_scanned(self, ssid: str, security: str, psk: Optional[str] = None) -> Optional[bytes]:
        if ssid == "BadNet":
            return b"Error: Connection activation failed: (7) Secrets were required, but not provided."
        existing = next((p for p in self._saved if p["ssid"] == ssid), None)
        if existing is None:
            name = self._resolve_unique_name(ssid)
            self._saved.append({"name": name, "ssid": ssid, "psk": psk or "", "timestamp": int(time.time())})
            self._active = name
        else:
            if psk is not None:
                existing["psk"] = psk
            existing["timestamp"] = int(time.time())
            self._active = existing["name"]
        self._hotspot_active = False
        self._refresh_status()
        return None

    def disconnect(self, name: str) -> Optional[bytes]:
        if name == self._active:
            self._active = None
            self._refresh_status()
        return None

    def connect_saved(self, name: str, wait: bool = True, reconnect: bool = False) -> Optional[bytes]:
        profile = next((p for p in self._saved if p["name"] == name), None)
        if profile is None:
            return b"Error: unknown connection " + name.encode("utf-8")
        if profile["ssid"] == "BadNet":
            return b"Error: Connection activation failed: (7) Secrets were required, but not provided."
        profile["timestamp"] = int(time.time())
        self._active = name
        self._hotspot_active = False
        self._refresh_status()
        return None

    def get_psk_for(self, name: str) -> Optional[str]:
        profile = next((p for p in self._saved if p["name"] == name), None)
        return profile["psk"] if profile else None

    def replace_psk(self, name: str, psk: str) -> Optional[bytes]:
        profile = next((p for p in self._saved if p["name"] == name), None)
        if profile is None:
            return b"Error: unknown connection " + name.encode("utf-8")
        profile["psk"] = psk
        return self.connect_saved(name)

    def delete_connection(self, name: str) -> Optional[bytes]:
        profile = next((p for p in self._saved if p["name"] == name), None)
        if profile is None:
            return b"Error: unknown connection " + name.encode("utf-8")
        self._saved.remove(profile)
        if self._active == name:
            self._active = None
            self._refresh_status()
        return None


class StubBluetoothManager(BluetoothManager):
    """In-memory bluetooth manager; no D-Bus connection and no bluez.

    Devices only become visible once discovery is running, mirroring the real
    thing: bluez publishes unpaired LE objects during a scan and purges them
    the moment it stops. 'Stubborn Speaker' is a tripwire — pairing it always
    fails, so the menu's error path is reachable in the emulator."""

    FAILING_NAME = "Stubborn Speaker"

    _NEARBY: list[BtDevice] = [
        BtDevice(
            path="/org/bluez/hci0/dev_D4_06_0F_EE_16_83",
            address="D4:06:0F:EE:16:83",
            name="EV-1-WL",
            kind=DeviceKind.MIDI,
            paired=False,
            connected=False,
            trusted=False,
            rssi=-52,
        ),
        BtDevice(
            path="/org/bluez/hci0/dev_C8_3B_44_10_02_9A",
            address="C8:3B:44:10:02:9A",
            name="R400 Presenter",
            kind=DeviceKind.INPUT,
            paired=False,
            connected=False,
            trusted=False,
            rssi=-71,
        ),
        BtDevice(
            path="/org/bluez/hci0/dev_11_22_33_44_55_66",
            address="11:22:33:44:55:66",
            name=FAILING_NAME,
            kind=DeviceKind.MIDI,
            paired=False,
            connected=False,
            trusted=False,
            rssi=-88,
        ),
    ]

    def __init__(self, on_status_change: Optional[Callable[[BtStatus], None]] = None) -> None:
        self.lock = threading.Lock()
        self.settings = None
        self.on_status_change = on_status_change
        self.last_status: BtStatus = {}
        self._last_sig: tuple = ()
        self._enabled: bool = True
        self._capable: bool = True
        self._discovering: bool = False
        self._known: list[KnownDevice] = []
        self._devices: dict[str, BtDevice] = {}
        self._off: set[str] = set()  # addresses whose device stopped advertising
        self._off_at: float = 0.0  # monotonic time it went dark
        self.queue: CommandQueue = CommandQueue(self)

    STALE_AFTER_S = 15.0  # mirrors BluezClient._STALE_AFTER_S

    def power_cycle(self, address: Optional[str] = None) -> None:
        """Simulate switching a device off mid-scan: it stops advertising, so
        it must vanish from the nearby list even though discovery keeps
        running (exactly what a real bluez never signals)."""
        live = [a for a, d in self._devices.items() if not d["paired"]]
        if address is None:
            address = live[0] if live else None
        if address is not None:
            self._off.add(address)
            self._off_at = time.monotonic()
        self.request_refresh()

    def _revive(self, address: Optional[str] = None) -> None:
        """Device powered back on: advertise again."""
        if address is None:
            self._off.clear()
        else:
            self._off.discard(address)
        self.request_refresh()

    # ----- overrides of the real manager's bluez-backed surface -----

    @property
    def supported(self) -> bool:
        return True

    @property
    def capable(self) -> bool:
        return self._capable

    def status(self) -> BtStatus:
        return BtStatus(
            supported=True,
            capable=self._capable,
            enabled=self._enabled,
            powered=self._enabled,
            discovering=self._discovering,
            connected=[d["name"] for d in self._devices.values() if d["connected"]],
        )

    def request_refresh(self) -> None:
        """Inherited poll() recomputes unconditionally; nothing to arm."""
        return

    def shutdown(self) -> None:
        try:
            self.queue.shutdown()
        except Exception:
            pass

    def devices(self) -> list[BtDevice]:
        now = time.monotonic()
        if self._off and now - self._off_at > self.STALE_AFTER_S:
            # Evict the ghosts, but keep the off set itself: the device is
            # still powered off, so a later scan must not resurrect it.
            self._devices = {a: d for a, d in self._devices.items() if a not in self._off}
            self._off_at = now
        return list(self._devices.values())

    def known_devices(self) -> list[KnownDevice]:
        return list(self._known)

    def remember(self, device: BtDevice) -> None:
        self._known = [k for k in self._known if k["address"] != device["address"]]
        self._known.append(
            KnownDevice(
                address=device["address"],
                name=device["name"],
                kind=device["kind"].value,
                last_connected=int(time.time()),
            )
        )

    def forget(self, address: str, name: str) -> None:
        self._known = [k for k in self._known if k["address"] != address]

    def set_enabled(self, enabled: bool) -> Optional[str]:
        self._enabled = enabled
        if not enabled:
            self._devices.clear()
            self._discovering = False
        self.request_refresh()
        return None

    def start_discovery(self) -> None:
        self._discovering = True
        for device in self._NEARBY:
            if device["address"] in self._off:
                continue  # powered off: nothing advertises, bluez has no object
            self._devices.setdefault(device["address"], device.copy())
        self.request_refresh()

    def stop_discovery(self) -> None:
        self._discovering = False
        # Unpaired objects do not survive the end of a scan.
        self._devices = {a: d for a, d in self._devices.items() if d["paired"]}
        self.request_refresh()

    def pair(self, device: BtDevice) -> None:
        if device["name"] == self.FAILING_NAME:
            raise RuntimeError("org.bluez.Error.AuthenticationFailed: stub refuses to pair")
        live = self._devices.setdefault(device["address"], device.copy())
        live["paired"] = True
        live["trusted"] = True
        live["connected"] = True
        self.remember(live)
        self.request_refresh()

    def connect(self, device: BtDevice) -> None:
        live = self._devices.setdefault(device["address"], device.copy())
        live["connected"] = True
        self.remember(live)
        self.request_refresh()

    def disconnect(self, device: BtDevice) -> None:
        live = self._devices.get(device["address"])
        if live is not None:
            live["connected"] = False
            live["paired"] = False  # the EV-1-WL's non-bonding behaviour
        self.request_refresh()

    def remove(self, device: BtDevice) -> None:
        self._devices.pop(device["address"], None)
        self.forget(device["address"], device["name"])
        self.request_refresh()


class StubEthernetManager(EthernetManager):
    """Pinned-up ethernet stub for the emulator.

    `carrier_up` is always True so the Wired Connection menu surface is always
    reachable. `service_active` is flipped locally by start/stop so the menu
    re-renders with the new state on the next poll tick — no real systemd unit
    is touched. The base class' background polling thread is not started; we
    override __init__ to skip it entirely so the emulator has no /sysfs or
    systemctl dependencies.
    """

    def __init__(self) -> None:
        # Deliberately skip super().__init__() — no thread, no sysfs polling.
        self.carrier_up = True
        self.service_active = False
        # Signal a single initial render so the menu picks up our fake state.
        self._changed = True
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def shutdown(self) -> None:
        pass

    def read_ipv4(self) -> Optional[str]:
        return "169.254.125.193/16"

    def read_jack_settings(self) -> tuple[Optional[int], Optional[int]]:
        return (48000, 128)

    def read_xrun_buckets(self) -> tuple[int, int, int]:
        return (0, 0, 0)

    def start_service(self) -> None:
        with self._lock:
            self.service_active = True
            self._changed = True

    def stop_service(self) -> None:
        with self._lock:
            self.service_active = False
            self._changed = True


class StubJackMute(JackMute):
    """In-memory mute state; no JACK calls. Lets the menu's Mute/Unmute MOD
    button visibly toggle in the emulator.

    Subclasses ``JackMute`` so test fixtures can assign it to
    ``handler.jack_mute`` (typed ``JackMute``) — matches the StubRelay
    pattern (subclass + override everything, no super().__init__).
    """

    def __init__(self) -> None:
        self._muted = False

    def is_muted(self) -> bool:
        return self._muted

    def mute(self) -> None:
        self._muted = True

    def unmute(self) -> None:
        self._muted = False


class StubRelay(pistomp.relay.Relay):
    """No-op relay; satisfies the Relay interface without GPIO."""

    def __init__(self):
        self.enabled = True

    def init_state(self):
        return self.enabled

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False

    def update(self, enable):
        self.enabled = enable

    def get(self):
        return self.enabled
