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

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from common.command_queue import Command

from .types import BtDevice

if TYPE_CHECKING:
    from .manager import BluetoothManager


@dataclass
class PowerCmd(Command[Optional[str]]):
    enabled: bool

    def run(self, mgr: "BluetoothManager") -> Optional[str]:
        return mgr.set_enabled(self.enabled)

    def key(self) -> str:
        return "power"


@dataclass
class InstallSupportCmd(Command[Optional[str]]):
    def run(self, mgr: "BluetoothManager") -> Optional[str]:
        return mgr.install_support()

    def key(self) -> str:
        return "install_support"


@dataclass
class StartDiscoveryCmd(Command[None]):
    """Opens discovery and returns — it does not block on results.

    BlueZ purges every unpaired LE device object the moment discovery stops,
    so discovery is held open for as long as the nearby list is on screen and
    Pair() is issued against a live object while it is still running. That is
    why this is not a blocking scan the way wifi's ScanCmd is."""

    def run(self, mgr: "BluetoothManager") -> None:
        mgr.start_discovery()

    def key(self) -> str:
        return "discovery"


@dataclass
class StopDiscoveryCmd(Command[None]):
    def run(self, mgr: "BluetoothManager") -> None:
        mgr.stop_discovery()

    def key(self) -> str:
        return "discovery"


@dataclass
class PairCmd(Command[None]):
    device: BtDevice

    def run(self, mgr: "BluetoothManager") -> None:
        mgr.pair(self.device)

    def key(self) -> str:
        return f"pair:{self.device['address']}"


@dataclass
class ConnectCmd(Command[None]):
    device: BtDevice

    def run(self, mgr: "BluetoothManager") -> None:
        mgr.connect(self.device)

    def key(self) -> str:
        return f"connect:{self.device['address']}"


@dataclass
class DisconnectCmd(Command[None]):
    device: BtDevice

    def run(self, mgr: "BluetoothManager") -> None:
        mgr.disconnect(self.device)

    def key(self) -> str:
        return f"disconnect:{self.device['address']}"


@dataclass
class ForgetCmd(Command[None]):
    device: BtDevice

    def run(self, mgr: "BluetoothManager") -> None:
        mgr.remove(self.device)

    def key(self) -> str:
        return f"forget:{self.device['address']}"
