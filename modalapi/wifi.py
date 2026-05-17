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
import threading
import subprocess
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Generic, Literal, Optional, TypedDict, TypeVar, cast


class KeyMgmt(str, Enum):
    """nmcli `802-11-wireless-security.key-mgmt` values."""

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
    """Split an nmcli `-t` line, unescaping `\\:` and `\\\\`."""
    fields: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            buf.append(line[i + 1])
            i += 2
            continue
        if ch == ":":
            fields.append("".join(buf))
            buf.clear()
            i += 1
            continue
        buf.append(ch)
        i += 1
    fields.append("".join(buf))
    return fields


TerseField = Literal[
    "GENERAL.STATE",
    "GENERAL.CONNECTION",
    "IP4.ADDRESS",
    "NAME",
    "UUID",
    "TYPE",
    "TIMESTAMP",
    "802-11-wireless.ssid",
    "802-11-wireless.mode",
    "802-11-wireless-security.psk",
    "IN-USE",
    "SSID",
    "SIGNAL",
    "SECURITY",
]


def _parse_kv_lines(stdout: str) -> dict[TerseField, str]:
    """Parse nmcli `-t` key:value output; empty and `--` values are dropped."""
    out: dict[TerseField, str] = {}
    for line in stdout.split("\n"):
        if not line:
            continue
        parts = _split_terse(line)
        if len(parts) < 2:
            continue
        key, value = parts[0], parts[1]
        if not value or value == "--":
            continue
        out[cast(TerseField, key)] = value
    return out


def _nmcli(
    args: list[str],
    *,
    sudo: bool = False,
    timeout: float = 20.0,
    terse_fields: Optional[list[TerseField]] = None,
    show_secrets: bool = False,
) -> tuple[Optional[str], Optional[bytes]]:
    """Run nmcli; returns `(stdout, None)` on success or `(None, error_bytes)` on any failure."""
    cmd: list[str] = ["sudo"] if sudo else []
    cmd.append("nmcli")
    if show_secrets:
        cmd.append("-s")
    if terse_fields is not None:
        cmd += ["-t", "-f", ",".join(terse_fields)]
    cmd += args
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, b"timed out"
    except Exception as e:
        return None, str(e).encode("utf-8", errors="replace")
    if result.returncode != 0:
        stderr = (result.stderr or "").strip() or "exit %d" % result.returncode
        return None, stderr.encode("utf-8", errors="replace")
    return result.stdout, None


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
        return wm.enable_hotspot()

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
        # `systemctl is-active` exits non-zero when inactive, so don't treat non-zero as failure.
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "wifi-hotspot"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() == "active"
        except Exception:
            return False

    def _get_wpa_status(self, status: WifiStatus) -> None:
        # `device show` rejects per-setting fields; fetch SSID via `connection show` below.
        stdout, err = _nmcli(
            ["device", "show", self.iface_name],
            terse_fields=["GENERAL.STATE", "GENERAL.CONNECTION", "IP4.ADDRESS"],
            timeout=10,
        )
        if err is not None or stdout is None:
            logging.error("nmcli device show failed: " + (err or b"").decode("utf-8", "replace"))
            return
        kv = _parse_kv_lines(stdout)
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

    def enable_hotspot(self) -> Optional[bytes]:
        try:
            subprocess.check_output(
                ["sudo", "systemctl", "enable", "--now", "wifi-hotspot"],
                stderr=subprocess.STDOUT,
                timeout=60,
            )
            return None
        except subprocess.CalledProcessError as exc:
            return exc.output
        except subprocess.TimeoutExpired:
            return b"hotspot enable timed out"

    def disable_hotspot(self) -> Optional[bytes]:
        """Stop the hotspot and reactivate the most-recent saved profile.
        NM doesn't reliably autoconnect after AP teardown. Returns None on
        success or when no saved profile exists; nmcli stderr otherwise."""
        try:
            subprocess.check_output(
                ["sudo", "systemctl", "disable", "--now", "wifi-hotspot"],
                stderr=subprocess.STDOUT,
                timeout=60,
            )
        except subprocess.CalledProcessError as exc:
            return exc.output
        except subprocess.TimeoutExpired:
            return b"hotspot disable timed out"

        saved = self.list_connections()
        if not saved:
            return None
        most_recent = max(saved, key=lambda c: c["timestamp"] or 0)
        return self.connect_saved(most_recent["name"], wait=False)

    def list_connections(self) -> list[SavedConnection]:
        """Return saved wifi client profiles, excluding hotspot (mode=ap) entries."""
        stdout, err = _nmcli(
            ["connection", "show"],
            terse_fields=["NAME", "UUID", "TYPE", "TIMESTAMP"],
            timeout=10,
        )
        if err is not None or stdout is None:
            logging.error("nmcli connection show failed: " + (err or b"").decode("utf-8", "replace"))
            return []
        connections: list[SavedConnection] = []
        for line in stdout.strip().split("\n"):
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

    def _wifi_profile_ssid_mode(self, uuid: str) -> tuple[str, str]:
        """Read SSID and mode for a single wifi profile. Returns ('', '') on error."""
        stdout, err = _nmcli(
            ["connection", "show", uuid],
            terse_fields=["802-11-wireless.ssid", "802-11-wireless.mode"],
            timeout=10,
        )
        if err is not None or stdout is None:
            return "", ""
        kv = _parse_kv_lines(stdout)
        return kv.get("802-11-wireless.ssid", ""), kv.get("802-11-wireless.mode", "")

    def scan_networks(self) -> list[ScannedNetwork]:
        """Return visible nearby networks, deduplicated by SSID (strongest wins), sorted by signal desc."""
        stdout, err = _nmcli(
            ["dev", "wifi", "list", "--rescan", "yes", "ifname", self.iface_name],
            terse_fields=["IN-USE", "SSID", "SIGNAL", "SECURITY"],
            timeout=15,
        )
        if err is not None or stdout is None:
            logging.error("nmcli dev wifi list failed: " + (err or b"").decode("utf-8", "replace"))
            return []

        best: dict[str, ScannedNetwork] = {}
        for line in stdout.strip().split("\n"):
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
        _, err = _nmcli(["connection", "delete", name], sudo=True, timeout=20)
        return err

    def connect_scanned(self, ssid: str, security: str, psk: Optional[str] = None) -> Optional[bytes]:
        """Create a profile for an SSID and activate it; on failure the new profile is deleted."""
        try:
            km = KeyMgmt.from_scan_security(security)
        except ValueError as e:
            return str(e).encode()
        if km == KeyMgmt.WPA_EAP:
            return b"enterprise (802.1X) wifi is not supported"
        if km in (KeyMgmt.WPA_PSK, KeyMgmt.SAE) and not psk:
            return b"password required"

        name = self._resolve_unique_name(ssid)
        add_args = [
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
            "connection.autoconnect",
            "yes",
        ]
        # nmcli treats wifi-sec.key-mgmt=none as WEP. For a genuinely open AP,
        # the wifi-sec section must be omitted entirely.
        if km != KeyMgmt.NONE:
            add_args += ["wifi-sec.key-mgmt", km]
        if km in (KeyMgmt.WPA_PSK, KeyMgmt.SAE) and psk:
            add_args += ["wifi-sec.psk", psk]
        _, err = _nmcli(add_args, sudo=True, timeout=20)
        if err is not None:
            return err

        _, err = _nmcli(["connection", "up", name], sudo=True, timeout=45)
        if err is None:
            return None
        _, del_err = _nmcli(["connection", "delete", name], sudo=True, timeout=20)
        if del_err is not None:
            logging.error("failed to delete partial profile %s: %s" % (name, del_err.decode("utf-8", "replace")))
        return err

    def disconnect(self, name: str) -> Optional[bytes]:
        """Bring down a saved profile without forgetting it."""
        _, err = _nmcli(["connection", "down", name], sudo=True, timeout=20)
        return err

    def connect_saved(self, name: str, wait: bool = True, reconnect: bool = False) -> Optional[bytes]:
        """Activate a saved profile; with wait=False, NM keeps retrying in the background."""
        if not reconnect and self._is_profile_activated(name):
            return None
        args = ["--wait", "0", "connection", "up", name] if not wait else ["connection", "up", name]
        _, err = _nmcli(args, sudo=True, timeout=45 if wait else 10)
        return err

    def _is_profile_activated(self, name: str) -> bool:
        stdout, err = _nmcli(
            ["connection", "show", name],
            terse_fields=["GENERAL.STATE"],
            timeout=5,
        )
        if err is not None or stdout is None:
            return False
        return _parse_kv_lines(stdout).get("GENERAL.STATE") == "activated"

    def replace_psk(self, name: str, psk: str) -> Optional[bytes]:
        """Set a new PSK and validate by activating; rolls back to the old PSK on failure."""
        old_psk = self.get_psk_for(name)
        _, err = _nmcli(
            ["connection", "modify", name, "802-11-wireless-security.psk", psk],
            sudo=True,
            timeout=20,
        )
        if err is not None:
            return err

        err = self.connect_saved(name, reconnect=True)
        if err is not None and old_psk is not None:
            _, rollback_err = _nmcli(
                ["connection", "modify", name, "802-11-wireless-security.psk", old_psk],
                sudo=True,
                timeout=20,
            )
            if rollback_err is not None:
                logging.error("PSK rollback failed: " + rollback_err.decode("utf-8", "replace"))
            else:
                logging.info("rolled back PSK on %s after failed connect" % name)
        return err

    def get_psk_for(self, name: str) -> Optional[str]:
        """Fetch the stored PSK for a wifi profile, or None if unavailable."""
        stdout, err = _nmcli(
            ["connection", "show", name],
            sudo=True,
            show_secrets=True,
            terse_fields=["802-11-wireless-security.psk"],
            timeout=10,
        )
        if err is not None or stdout is None:
            return None
        return _parse_kv_lines(stdout).get("802-11-wireless-security.psk") or None
