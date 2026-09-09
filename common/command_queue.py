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

"""Serialized background executor shared by the wifi and bluetooth managers.

Commands run one at a time on a worker thread; results are delivered on the
main thread via poll(). The manager it runs against is duck-typed to
CommandContext, so neither subsystem has to know about the other."""

import logging
import queue
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable, Generic, Protocol, TypeVar

from common.util import TEARDOWN_JOIN_S

T = TypeVar("T")


class CommandContext(Protocol):
    """What CommandQueue needs of the manager it executes against."""

    def request_refresh(self) -> None: ...


class Command(ABC, Generic[T]):
    """A unit of serialized work. Deduped by key() — if a command with the
    same key is pending or in-flight, a fresh submission is dropped."""

    # Positional-only so subclasses are free to name (and narrow) the manager.
    @abstractmethod
    def run(self, ctx: Any, /) -> T: ...

    @abstractmethod
    def key(self) -> str: ...


_SHUTDOWN_SENTINEL = object()


class CommandQueue:
    """Serialized executor over a manager. Worker thread runs Commands;
    results are delivered on the main thread via poll(). Dedupes by key()."""

    def __init__(self, ctx: CommandContext) -> None:
        self._ctx = ctx
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
                result = cmd.run(self._ctx)
            except Exception as e:
                logging.exception("Command failed: %s", cmd)
                result = e
            with self._lock:
                self._pending_keys.discard(cmd.key())
                if bumps_pending:
                    self._pending_op_count -= 1
            if bumps_pending:
                # Nudge the poller for fresh status — don't wait out the tick.
                try:
                    self._ctx.request_refresh()
                except Exception:
                    logging.exception("Status refresh request failed")
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
                logging.exception("Command result callback failed")

    def pending_op_count(self) -> int:
        with self._lock:
            return self._pending_op_count

    def shutdown(self, join: bool = True) -> None:
        self._cmd_queue.put(_SHUTDOWN_SENTINEL)
        if join:
            self._worker.join(timeout=TEARDOWN_JOIN_S)
