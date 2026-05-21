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
from typing import Optional, TypedDict


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
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:80]
    return "unknown error"
