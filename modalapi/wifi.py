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
#
# Parts of this file borrowed from patchbox-cli
#
# Copyright (C) 2017  Vilniaus Blokas UAB, https://blokas.io/pisound

import os
import queue
import re
import threading
import subprocess
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Generic, Optional, TypedDict, TypeVar


class KeyMgmt(str, Enum):
    """nmcli `802-11-wireless-security.key-mgmt` values. Subclasses `str` so
    instances drop straight into subprocess arg lists."""

    WPA_PSK = "wpa-psk"
    SAE = "sae"
    WPA_EAP = "wpa-eap"
    NONE = "none"

    @classmethod
    def from_scan_security(cls, security: str) -> "KeyMgmt":
        """Map an `nmcli dev wifi list` SECURITY token to a key-mgmt value.

        Raises ValueError for security types we don't support (WEP, unknown)."""
        s = (security or "").upper().strip()
        if not s or s == "--":
            return cls.NONE
        if "SAE" in s or "WPA3" in s:
            return cls.SAE
        if "802.1X" in s or "EAP" in s:
            return cls.WPA_EAP
        if "WPA" in s or "PSK" in s:
            return cls.WPA_PSK
        raise ValueError(f"unsupported wifi security: {security!r}")


class SavedConnection(TypedDict):
    name: str
    ssid: str
    timestamp: int


class ScannedNetwork(TypedDict):
    ssid: str
    signal: int
    security: str
    in_use: bool


class WifiStatus(TypedDict, total=False):
    wifi_supported: bool
    wifi_connected: bool
    hotspot_active: bool
    state: str
    connection: str
    ip4_address: str
    ssid: str


def parse_nmcli_error(stderr: Optional[bytes | str]) -> str:
    """Map a chunk of nmcli stderr to a short user-facing reason."""
    if stderr is None:
        return "unknown error"
    text = stderr.decode("utf-8", errors="replace") if isinstance(stderr, (bytes, bytearray)) else str(stderr)
    lower = text.lower()
    if "secrets were required" in lower or "802-11-wireless-security.psk" in lower or "(7)" in lower:
        return "auth failed (wrong password)"
    if "no network with ssid" in lower or "no suitable" in lower or "ssid not found" in lower:
        return "network not found"
    if "ip-config-unavailable" in lower or "dhcp" in lower:
        return "couldn't get an IP (DHCP timeout)"
    if "timeout" in lower or "timed out" in lower:
        return "timed out"
    if "not authorized" in lower or "permission denied" in lower:
        return "permission denied"
    # Fall back to first non-empty line, truncated.
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:80]
    return "unknown error"


def _split_terse(line: str) -> list[str]:
    """Split an nmcli -t terse line, honouring backslash-escaped colons."""
    return [p.replace("\\:", ":") for p in re.split(r"(?<!\\):", line)]


C = TypeVar("C")
T = TypeVar("T")


class Command(ABC, Generic[C, T]):
    """A unit of serialized work. Subclasses carry their args as fields.

    `run(ctx)` does the blocking work on a worker thread, given a context
    object held by the queue. `key()` is the dedup identity — if a command
    with the same key is already pending or in-flight, a fresh submission
    is silently dropped.
    """

    @abstractmethod
    def run(self, ctx: C, /) -> T: ...

    @abstractmethod
    def key(self) -> str: ...


@dataclass
class ConnectSavedCmd(Command["WifiManager", Optional[bytes]]):
    name: str
    ssid: str
    wait: bool = True

    def run(self, wm: "WifiManager") -> Optional[bytes]:
        return wm.connect_saved(self.name, wait=self.wait)

    def key(self) -> str:
        return f"connect:{self.ssid}"


@dataclass
class ConnectScannedCmd(Command["WifiManager", Optional[bytes]]):
    ssid: str
    security: str
    psk: Optional[str]

    def run(self, wm: "WifiManager") -> Optional[bytes]:
        return wm.connect_scanned(self.ssid, self.security, self.psk)

    def key(self) -> str:
        return f"connect:{self.ssid}"


@dataclass
class ReplacePskCmd(Command["WifiManager", Optional[bytes]]):
    name: str
    ssid: str
    psk: str

    def run(self, wm: "WifiManager") -> Optional[bytes]:
        return wm.replace_psk(self.name, self.psk)

    def key(self) -> str:
        return f"connect:{self.ssid}"


@dataclass
class DisconnectCmd(Command["WifiManager", Optional[bytes]]):
    name: str
    ssid: str

    def run(self, wm: "WifiManager") -> Optional[bytes]:
        return wm.disconnect(self.name)

    def key(self) -> str:
        return f"disconnect:{self.ssid}"


@dataclass
class ForgetCmd(Command["WifiManager", Optional[bytes]]):
    name: str
    ssid: str

    def run(self, wm: "WifiManager") -> Optional[bytes]:
        return wm.delete_connection(self.name)

    def key(self) -> str:
        return f"forget:{self.ssid}"


@dataclass
class ToggleHotspotCmd(Command["WifiManager", Optional[bytes]]):
    was_active: bool

    def run(self, wm: "WifiManager") -> Optional[bytes]:
        if self.was_active:
            return wm.disable_hotspot()
        wm.enable_hotspot()
        return None

    def key(self) -> str:
        return "toggle_hotspot"


@dataclass
class ScanCmd(Command["WifiManager", list]):
    def run(self, wm: "WifiManager") -> list:
        return wm.scan_networks()

    def key(self) -> str:
        return "scan"


_SHUTDOWN_SENTINEL = object()


class CommandQueue(Generic[C]):
    """Serialized executor over a fixed context. Drains submitted Commands
    on a single daemon worker; delivers results on the main thread via poll().

    Dedupes by Command.key(): a submission whose key matches a queued or
    in-flight item is silently dropped. State-changing submissions bump
    pending_op_count; scan submissions do not.
    """

    def __init__(self, context: C) -> None:
        self._context: C = context
        self._cmd_queue: queue.Queue = queue.Queue()
        self._result_queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._pending_op_count = 0
        self._pending_keys: set[str] = set()
        self._worker = threading.Thread(target=self._drain, daemon=True)
        self._worker.start()

    def submit(self, cmd: Command[C, T], on_done: Callable[[T], None]) -> bool:
        return self._enqueue(cmd, on_done, bumps_pending=True)

    def submit_scan(self, cmd: Command[C, T], on_done: Callable[[T], None]) -> bool:
        return self._enqueue(cmd, on_done, bumps_pending=False)

    def _enqueue(self, cmd: Command, on_done: Callable, bumps_pending: bool) -> bool:
        key = cmd.key()
        with self._lock:
            if key in self._pending_keys:
                return False
            self._pending_keys.add(key)
            if bumps_pending:
                self._pending_op_count += 1
        self._cmd_queue.put((cmd, on_done, bumps_pending))
        return True

    def _drain(self) -> None:
        while True:
            item = self._cmd_queue.get()
            if item is _SHUTDOWN_SENTINEL:
                return
            cmd, on_done, bumps_pending = item
            try:
                result = cmd.run(self._context)
            except Exception as e:
                logging.exception("Command failed: %s", cmd)
                result = e
            with self._lock:
                self._pending_keys.discard(cmd.key())
                if bumps_pending:
                    self._pending_op_count -= 1
            self._result_queue.put((on_done, result))

    def poll(self) -> None:
        assert threading.current_thread() is threading.main_thread(), "CommandQueue.poll() must run on the main thread"
        while True:
            try:
                on_done, result = self._result_queue.get_nowait()
            except queue.Empty:
                return
            try:
                on_done(result)
            except Exception:
                logging.exception("Wifi result callback failed")

    def pending_op_count(self) -> int:
        with self._lock:
            return self._pending_op_count

    def shutdown(self) -> None:
        self._cmd_queue.put(_SHUTDOWN_SENTINEL)
        self._worker.join(timeout=2.0)


class WifiManager:
    # Hard-wire wifi interface to avoid scrubbing sysfs; the hotspot scripts
    # are likewise hard-wired.
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
        self.queue: CommandQueue["WifiManager"] = CommandQueue(self)
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
        # Once we know it's supported, no need to check the file again
        if self.wireless_supported:
            return True
        self.wireless_supported = os.path.exists(self.wireless_file)
        return self.wireless_supported

    def _is_wifi_connected(self) -> bool:
        try:
            with open(self.operstate_file) as f:
                line = f.readline()
                return line.startswith("up")
        except Exception:
            return False

    def _is_hotspot_active(self) -> bool:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "wifi-hotspot"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            return result.stdout.strip() == "active"
        except Exception:
            return False

    def _get_wpa_status(self, status: WifiStatus) -> None:
        # `nmcli device show` rejects per-setting fields like 802-11-wireless.ssid;
        # those are only valid on `connection show <id>`. Fetch the SSID separately
        # once we know which profile is active.
        try:
            result = subprocess.run(
                [
                    "nmcli",
                    "-t",
                    "-f",
                    "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS",
                    "device",
                    "show",
                    self.iface_name,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as e:
            logging.error("NetworkManager status fail:" + str(e))
            return
        if result.returncode != 0:
            return
        for line in result.stdout.strip().split("\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key == "GENERAL.STATE":
                status["state"] = value
            elif key == "GENERAL.CONNECTION":
                status["connection"] = value
            elif key == "IP4.ADDRESS" or key.startswith("IP4.ADDRESS["):
                status["ip4_address"] = value
        connection = status.get("connection")
        if connection and connection != "--":
            ssid, _ = self._wifi_profile_ssid_mode(connection)
            if ssid:
                status["ssid"] = ssid

    def _polling_thread(self) -> None:
        while True:
            new_status: WifiStatus = {}
            supported = new_status["wifi_supported"] = self._is_wifi_supported()
            connected = new_status["wifi_connected"] = self._is_wifi_connected()
            hp_active = new_status["hotspot_active"] = self._is_hotspot_active()
            if supported and (connected or hp_active):
                self._get_wpa_status(new_status)

            saved = self.list_connections() if supported else []

            with self.lock:
                self._cached_saved = saved
                if new_status != self.last_status:
                    logging.debug("Wifi status changed:" + str(new_status))
                    self.last_status = new_status
                    self.changed = True

            # loop wait
            if self.stop.wait(5.0):
                break

    # External API
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

    def enable_hotspot(self) -> None:
        try:
            subprocess.check_output(
                ["sudo", "systemctl", "enable", "--now", "wifi-hotspot"], timeout=60
            ).strip().decode("utf-8")
        except Exception:
            logging.debug("Wifi hotspot enabling failed")

    def disable_hotspot(self) -> Optional[bytes]:
        """Stop the hotspot and reactivate the most-recent saved profile.
        NM doesn't reliably autoconnect after AP teardown. Returns None on
        success or when no saved profile exists; nmcli stderr otherwise."""
        try:
            subprocess.check_output(["sudo", "systemctl", "disable", "--now", "wifi-hotspot"], timeout=60)
        except Exception:
            logging.debug("Wifi hotspot disabling failed")

        saved = self.list_connections()
        if not saved:
            return None
        most_recent = max(saved, key=lambda c: c["timestamp"] or 0)
        return self.connect_saved(most_recent["name"], wait=False)

    # nmcli's bulk `connection show` only accepts these column names with `-f`.
    # Per-setting property fields (e.g. 802-11-wireless.ssid) are valid only on
    # `connection show <uuid>`, so we read those separately per-profile.
    _BULK_CONN_FIELDS = ("NAME", "UUID", "TYPE", "TIMESTAMP")

    def list_connections(self) -> list[SavedConnection]:
        """Return saved wifi client profiles. Filter by mode=ap so both images'
        hotspot profile names (`pistomp-hotspot`, `Hotspot`) are excluded."""
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", ",".join(self._BULK_CONN_FIELDS), "connection", "show"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode != 0:
                logging.error("nmcli connection show failed: " + result.stderr.strip())
                return []
            connections: list[SavedConnection] = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = _split_terse(line)
                if len(parts) < 4 or parts[2] != "802-11-wireless":
                    continue
                name, uuid = parts[0], parts[1]
                try:
                    timestamp = int(parts[3]) if parts[3] else 0
                except ValueError:
                    timestamp = 0
                ssid, mode = self._wifi_profile_ssid_mode(uuid)
                if mode == "ap":
                    continue
                connections.append(SavedConnection(name=name, ssid=ssid or name, timestamp=timestamp))
            return connections
        except Exception as e:
            logging.error("Failed to list wifi connections: " + str(e))
            return []

    def _wifi_profile_ssid_mode(self, uuid: str) -> tuple[str, str]:
        """Read SSID and mode for a single wifi profile. Returns ('', '') on error."""
        try:
            result = subprocess.run(
                [
                    "nmcli",
                    "-t",
                    "-f",
                    "802-11-wireless.ssid,802-11-wireless.mode",
                    "connection",
                    "show",
                    uuid,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as e:
            logging.error("nmcli connection show %s failed: %s" % (uuid, e))
            return "", ""
        if result.returncode != 0:
            return "", ""
        ssid = mode = ""
        for line in result.stdout.split("\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key == "802-11-wireless.ssid":
                ssid = value
            elif key == "802-11-wireless.mode":
                mode = value
        return ssid, mode

    def scan_networks(self) -> list[ScannedNetwork]:
        """Return visible nearby networks, deduplicated by SSID (strongest wins), sorted by signal desc."""
        try:
            result = subprocess.run(
                [
                    "nmcli",
                    "-t",
                    "-f",
                    "IN-USE,SSID,SIGNAL,SECURITY",
                    "dev",
                    "wifi",
                    "list",
                    "--rescan",
                    "auto",
                    "ifname",
                    self.iface_name,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15,
            )
        except Exception as e:
            logging.error("wifi scan failed: " + str(e))
            return []

        best: dict[str, ScannedNetwork] = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = _split_terse(line)
            if len(parts) < 4:
                continue
            in_use = parts[0] == "*"
            ssid = parts[1]
            if not ssid:
                continue  # hidden network
            try:
                signal = int(parts[2])
            except ValueError:
                signal = 0
            security = parts[3]
            existing = best.get(ssid)
            if existing is None or signal > existing["signal"]:
                best[ssid] = ScannedNetwork(ssid=ssid, signal=signal, security=security, in_use=in_use)
            elif in_use:
                existing["in_use"] = True
        return sorted(best.values(), key=lambda n: n["signal"], reverse=True)

    def _resolve_unique_name(self, desired: str) -> str:
        """Pick a profile name based on `desired`, suffixing (2)/(3)/... on collision."""
        existing = {c["name"] for c in self.list_connections()}
        name = desired
        counter = 2
        while name in existing:
            name = "%s (%d)" % (desired, counter)
            counter += 1
        return name

    def delete_connection(self, name: str) -> Optional[bytes]:
        """Delete a wifi profile by its NM connection name."""
        try:
            subprocess.check_output(["sudo", "nmcli", "connection", "delete", name], stderr=subprocess.STDOUT)
            return None
        except subprocess.CalledProcessError as exc:
            return exc.output

    def connect_scanned(self, ssid: str, security: str, psk: Optional[str] = None) -> Optional[bytes]:
        """Create a profile for an SSID and activate it. `security` is the SECURITY
        column from `nmcli dev wifi list` (or, for the Join dialog, an SSID-less
        caller's best guess: "WPA2" if a psk was entered, "" for open).

        On failure the freshly-created profile is deleted so this doubles as a
        credential test — without ever touching an unrelated pre-existing profile
        with the same SSID (e.g. the OEM "preconfigured" entry)."""
        try:
            km = KeyMgmt.from_scan_security(security)
        except ValueError as e:
            return str(e).encode()
        if km == KeyMgmt.WPA_EAP:
            return b"enterprise (802.1X) wifi is not supported"
        if km in (KeyMgmt.WPA_PSK, KeyMgmt.SAE) and not psk:
            return b"password required"

        name = self._resolve_unique_name(ssid)
        add_cmd = [
            "sudo",
            "nmcli",
            "connection",
            "add",
            "type",
            "wifi",
            "ifname",
            self.iface_name,
            "con-name",
            name,
            "ssid",
            ssid,
            "wifi-sec.key-mgmt",
            km,
            "connection.autoconnect",
            "yes",
        ]
        if km in (KeyMgmt.WPA_PSK, KeyMgmt.SAE) and psk:
            add_cmd += ["wifi-sec.psk", psk]
        try:
            subprocess.check_output(add_cmd, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as exc:
            return exc.output

        try:
            subprocess.check_output(
                ["sudo", "nmcli", "connection", "up", name],
                stderr=subprocess.STDOUT,
                timeout=45,
            )
            return None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            err = exc.output if isinstance(exc, subprocess.CalledProcessError) else b"connection timed out"
            try:
                subprocess.check_output(
                    ["sudo", "nmcli", "connection", "delete", name],
                    stderr=subprocess.STDOUT,
                )
            except subprocess.CalledProcessError as del_exc:
                logging.error("failed to delete partial profile %s: %s" % (name, del_exc.output))
            return err

    def disconnect(self, name: str) -> Optional[bytes]:
        """Bring down a saved profile without forgetting it."""
        try:
            subprocess.check_output(["sudo", "nmcli", "connection", "down", name], stderr=subprocess.STDOUT, timeout=20)
            return None
        except subprocess.CalledProcessError as exc:
            return exc.output
        except subprocess.TimeoutExpired:
            return b"disconnect timed out"

    def connect_saved(self, name: str, wait: bool = True, reconnect: bool = False) -> Optional[bytes]:
        """Activate an existing saved profile. With wait=False, fire-and-forget
        via `nmcli --wait 0`: NM keeps trying in the background; only the
        request-validity error is surfaced. If the profile is already activated,
        only re-connects if reconnect=True."""
        if not reconnect and self._is_profile_activated(name):
            return None
        cmd = ["sudo", "nmcli"]
        if not wait:
            cmd += ["--wait", "0"]
        cmd += ["connection", "up", name]
        try:
            subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=45 if wait else 10)
            return None
        except subprocess.CalledProcessError as exc:
            return exc.output
        except subprocess.TimeoutExpired:
            return b"connection timed out"

    def _is_profile_activated(self, name: str) -> bool:
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "GENERAL.STATE", "connection", "show", name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
        except Exception:
            return False
        if result.returncode != 0:
            return False
        for line in result.stdout.split("\n"):
            if line.startswith("GENERAL.STATE:"):
                return line.split(":", 1)[1].strip() == "activated"
        return False

    def replace_psk(self, name: str, psk: str) -> Optional[bytes]:
        """Update the PSK on a saved profile and validate by activating it.

        On failure the previous PSK is restored so the saved profile keeps working."""
        old_psk = self.get_psk_for(name)
        try:
            subprocess.check_output(
                ["sudo", "nmcli", "connection", "modify", name, "802-11-wireless-security.psk", psk],
                stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError as exc:
            return exc.output

        err = self.connect_saved(name, reconnect=True)
        if err is not None and old_psk is not None:
            try:
                subprocess.check_output(
                    ["sudo", "nmcli", "connection", "modify", name, "802-11-wireless-security.psk", old_psk],
                    stderr=subprocess.STDOUT,
                )
                logging.info("rolled back PSK on %s after failed connect" % name)
            except subprocess.CalledProcessError as rollback_exc:
                logging.error("PSK rollback failed: " + str(rollback_exc.output))
        return err

    def get_psk_for(self, name: str) -> Optional[str]:
        """Fetch the stored PSK for a specific wifi profile."""
        try:
            result = subprocess.run(
                ["sudo", "nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show", name],
                stdout=subprocess.PIPE,
                text=True,
            )
            return result.stdout.strip() or None
        except Exception:
            return None
