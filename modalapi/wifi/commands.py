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
import queue
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Generic, Optional, TypeVar

if TYPE_CHECKING:
    from .manager import WifiManager

T = TypeVar("T")


class Command(ABC, Generic[T]):
    """A unit of serialized work. Subclasses carry their args as fields.

    `run(wm)` does the blocking work on a worker thread. `key()` is the dedup
    identity — if a command with the same key is already pending or in-flight,
    a fresh submission is silently dropped.
    """

    @abstractmethod
    def run(self, wm: "WifiManager") -> T: ...

    @abstractmethod
    def key(self) -> str: ...


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
    def run(self, wm: "WifiManager") -> list:
        return wm.scan_networks()

    def key(self) -> str:
        return "scan"


_SHUTDOWN_SENTINEL = object()


class CommandQueue:
    """Serialized executor over a WifiManager. Drains submitted Commands on a
    single daemon worker; delivers results on the main thread via poll().

    Dedupes by Command.key(): a submission whose key matches a queued or
    in-flight item is silently dropped. State-changing submissions bump
    pending_op_count; scan submissions do not.
    """

    def __init__(self, wm: "WifiManager") -> None:
        self._wm = wm
        self._cmd_queue: queue.Queue = queue.Queue()
        self._result_queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._pending_op_count = 0
        self._pending_keys: set[str] = set()
        self._worker = threading.Thread(target=self._drain, daemon=True)
        self._worker.start()

    def submit(self, cmd: "Command[T]", on_done: Callable[[T], None]) -> bool:
        return self._enqueue(cmd, on_done, bumps_pending=True)

    def submit_scan(self, cmd: "Command[T]", on_done: Callable[[T], None]) -> bool:
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
                result = cmd.run(self._wm)
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
