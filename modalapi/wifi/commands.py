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

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from common.command_queue import Command


if TYPE_CHECKING:
    from .manager import WifiManager


@dataclass
class ConnectSavedCmd(Command[Optional[bytes]]):
    name: str
    ssid: str
    wait: bool = True

    def run(self, wm: "WifiManager") -> Optional[bytes]:
        return wm.connect_saved(self.name, wait=self.wait)

    def key(self) -> str:
        return f"connect:{self.ssid}"


@dataclass
class ConnectScannedCmd(Command[Optional[bytes]]):
    ssid: str
    security: str
    psk: Optional[str]

    def run(self, wm: "WifiManager") -> Optional[bytes]:
        return wm.connect_scanned(self.ssid, self.security, self.psk)

    def key(self) -> str:
        return f"connect:{self.ssid}"


@dataclass
class ReplacePskCmd(Command[Optional[bytes]]):
    name: str
    ssid: str
    psk: str

    def run(self, wm: "WifiManager") -> Optional[bytes]:
        return wm.replace_psk(self.name, self.psk)

    def key(self) -> str:
        return f"connect:{self.ssid}"


@dataclass
class DisconnectCmd(Command[Optional[bytes]]):
    name: str
    ssid: str

    def run(self, wm: "WifiManager") -> Optional[bytes]:
        return wm.disconnect(self.name)

    def key(self) -> str:
        return f"disconnect:{self.ssid}"


@dataclass
class ForgetCmd(Command[Optional[bytes]]):
    name: str
    ssid: str

    def run(self, wm: "WifiManager") -> Optional[bytes]:
        return wm.delete_connection(self.name)

    def key(self) -> str:
        return f"forget:{self.ssid}"


@dataclass
class ToggleHotspotCmd(Command[Optional[bytes]]):
    was_active: bool

    def run(self, wm: "WifiManager") -> Optional[bytes]:
        if self.was_active:
            return wm.disable_hotspot()
        return wm.enable_hotspot()

    def key(self) -> str:
        return "toggle_hotspot"


@dataclass
class ScanCmd(Command[list]):
    """Trigger a fresh scan and return the results. Blocks for seconds."""

    def run(self, wm: "WifiManager") -> list:
        return wm.scan_networks()

    def key(self) -> str:
        return "scan"

