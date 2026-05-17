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
import subprocess
from typing import Optional

from .nmcli import TerseField, nmcli, parse_kv_lines, split_terse
from .types import KeyMgmt, SavedConnection, ScannedNetwork


def list_connections() -> list[SavedConnection]:
    """Return saved wifi client profiles, excluding hotspot (mode=ap) entries."""
    stdout, err = nmcli(
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
        parts = split_terse(line)
        if len(parts) < 4 or parts[2] != "802-11-wireless":
            continue
        name, uuid = parts[0], parts[1]
        try:
            timestamp = int(parts[3]) if parts[3] else 0
        except ValueError:
            timestamp = 0
        ssid, mode = wifi_profile_ssid_mode(uuid)
        if mode == "ap":
            continue
        connections.append(SavedConnection(name=name, ssid=ssid or name, timestamp=timestamp))
    return connections


def wifi_profile_ssid_mode(uuid: str) -> tuple[str, str]:
    """Read SSID and mode for a single wifi profile. Returns ('', '') on error."""
    stdout, err = nmcli(
        ["connection", "show", uuid],
        terse_fields=["802-11-wireless.ssid", "802-11-wireless.mode"],
        timeout=10,
    )
    if err is not None or stdout is None:
        return "", ""
    kv = parse_kv_lines(stdout)
    return kv.get("802-11-wireless.ssid", ""), kv.get("802-11-wireless.mode", "")


def scan_networks(iface_name: str) -> list[ScannedNetwork]:
    """Return visible nearby networks, deduplicated by SSID (strongest wins), sorted by signal desc."""
    stdout, err = nmcli(
        ["dev", "wifi", "list", "--rescan", "yes", "ifname", iface_name],
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
        parts = split_terse(line)
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


def resolve_unique_name(desired: str) -> str:
    """Pick a profile name based on `desired`, suffixing (2)/(3)/... on collision."""
    existing = {c["name"] for c in list_connections()}
    name = desired
    counter = 2
    while name in existing:
        name = "%s (%d)" % (desired, counter)
        counter += 1
    return name


def delete_connection(name: str) -> Optional[bytes]:
    """Delete a wifi profile by its NM connection name."""
    _, err = nmcli(["connection", "delete", name], sudo=True, timeout=20)
    return err


def connect_scanned(iface_name: str, ssid: str, security: str, psk: Optional[str] = None) -> Optional[bytes]:
    """Create a profile for an SSID and activate it; on failure the new profile is deleted.
    Stops the hotspot service first if it's active, so the AP doesn't fight the new client connection."""
    try:
        km = KeyMgmt.from_scan_security(security)
    except ValueError as e:
        return str(e).encode()
    if km == KeyMgmt.WPA_EAP:
        return b"enterprise (802.1X) wifi is not supported"
    if km in (KeyMgmt.WPA_PSK, KeyMgmt.SAE) and not psk:
        return b"password required"

    err = stop_hotspot_service()
    if err is not None:
        logging.warning("stop_hotspot_service before connect_scanned failed: %s", err.decode("utf-8", "replace"))

    name = resolve_unique_name(ssid)
    add_args = [
        "connection", "add", "type", "wifi",
        "ifname", iface_name,
        "con-name", name,
        "ssid", ssid,
        "connection.autoconnect", "yes",
    ]
    # nmcli treats wifi-sec.key-mgmt=none as WEP. For a genuinely open AP,
    # the wifi-sec section must be omitted entirely.
    if km != KeyMgmt.NONE:
        add_args += ["wifi-sec.key-mgmt", km]
    if km in (KeyMgmt.WPA_PSK, KeyMgmt.SAE) and psk:
        add_args += ["wifi-sec.psk", psk]
    _, err = nmcli(add_args, sudo=True, timeout=20)
    if err is not None:
        return err

    _, err = nmcli(["connection", "up", name], sudo=True, timeout=45)
    if err is None:
        return None
    _, del_err = nmcli(["connection", "delete", name], sudo=True, timeout=20)
    if del_err is not None:
        logging.error("failed to delete partial profile %s: %s" % (name, del_err.decode("utf-8", "replace")))
    return err


def disconnect(name: str) -> Optional[bytes]:
    """Bring down a saved profile without forgetting it."""
    _, err = nmcli(["connection", "down", name], sudo=True, timeout=20)
    return err


def is_profile_activated(name: str) -> bool:
    stdout, err = nmcli(
        ["connection", "show", name],
        terse_fields=["GENERAL.STATE"],
        timeout=5,
    )
    if err is not None or stdout is None:
        return False
    return parse_kv_lines(stdout).get("GENERAL.STATE") == "activated"


def connect_saved(name: str, wait: bool = True, reconnect: bool = False) -> Optional[bytes]:
    """Activate a saved profile; with wait=False, NM keeps retrying in the background.
    Stops the hotspot service first if it's active, so the AP doesn't fight the client connection."""
    if not reconnect and is_profile_activated(name):
        return None
    err = stop_hotspot_service()
    if err is not None:
        logging.warning("stop_hotspot_service before connect_saved failed: %s", err.decode("utf-8", "replace"))
    args = ["--wait", "0", "connection", "up", name] if not wait else ["connection", "up", name]
    _, err = nmcli(args, sudo=True, timeout=45 if wait else 10)
    return err


def get_psk_for(name: str) -> Optional[str]:
    """Fetch the stored PSK for a wifi profile, or None if unavailable."""
    stdout, err = nmcli(
        ["connection", "show", name],
        sudo=True,
        show_secrets=True,
        terse_fields=["802-11-wireless-security.psk"],
        timeout=10,
    )
    if err is not None or stdout is None:
        return None
    return parse_kv_lines(stdout).get("802-11-wireless-security.psk") or None


def replace_psk(name: str, psk: str) -> Optional[bytes]:
    """Set a new PSK and validate by activating; rolls back to the old PSK on failure."""
    old_psk = get_psk_for(name)
    _, err = nmcli(
        ["connection", "modify", name, "802-11-wireless-security.psk", psk],
        sudo=True,
        timeout=20,
    )
    if err is not None:
        return err

    err = connect_saved(name, reconnect=True)
    if err is not None and old_psk is not None:
        _, rollback_err = nmcli(
            ["connection", "modify", name, "802-11-wireless-security.psk", old_psk],
            sudo=True,
            timeout=20,
        )
        if rollback_err is not None:
            logging.error("PSK rollback failed: " + rollback_err.decode("utf-8", "replace"))
        else:
            logging.info("rolled back PSK on %s after failed connect" % name)
    return err


def stop_hotspot_service() -> Optional[bytes]:
    """Stop and disable the wifi-hotspot service without any recovery/reconnect logic.
    Idempotent: succeeds when the service is already inactive/disabled."""
    try:
        subprocess.check_output(
            ["sudo", "systemctl", "disable", "--now", "wifi-hotspot"],
            stderr=subprocess.STDOUT,
            timeout=60,
        )
        return None
    except subprocess.CalledProcessError as exc:
        return exc.output
    except subprocess.TimeoutExpired:
        return b"hotspot disable timed out"


def enable_hotspot() -> Optional[bytes]:
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


def disable_hotspot() -> Optional[bytes]:
    """Stop the hotspot and reactivate the most-recent saved profile.
    NM doesn't reliably autoconnect after AP teardown. Returns None on
    success or when no saved profile exists; nmcli stderr otherwise."""
    err = stop_hotspot_service()
    if err is not None:
        return err

    saved = list_connections()
    if not saved:
        return None
    most_recent = max(saved, key=lambda c: c["timestamp"] or 0)
    return connect_saved(most_recent["name"], wait=False)
