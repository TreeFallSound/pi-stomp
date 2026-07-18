# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-Stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Ableton Link / MIDI clock sync source — the device-side counterpart to
`ableton-link.md`. The transport WebSocket message carries a `syncMode`
label ("Internal" / "link" / "midi_clock_slave"); this module owns the
canonical enum, the wire↔enum normalization, and the off-UI-thread POST
that asks mod-ui to switch source.

The single-writer rule (CLAUDE.md) holds: we emit a `set_sync_mode` POST
optimistically and reconcile against the next transport echo — `sync_mode`
on the handler is *never* written locally outside the echo path, except for
the optimistic mirror in `set_sync_mode` which is what we expect mod-ui to
echo back. If mod-ui rejects the switch (e.g. Hylia unavailable) the echo
brings us back to the prior value.
"""

from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from collections.abc import Callable

    import pistomp.httpclient as req


class SyncMode(Enum):
    """The clock source owning tempo, as mod-ui sees it.

    The wire labels are mod-ui's (`TRANSPORT_SOURCE_*` in `mod/profile.py`);
    we keep the enum names independent of that vocabulary so the device code
    doesn't grow a dependency on mod-ui's Python layer.
    """

    INTERNAL = "Internal"
    LINK = "link"
    MIDI_CLOCK_SLAVE = "midi_clock_slave"

    @property
    def wire(self) -> str:
        return self.value

    @classmethod
    def parse(cls, raw: str) -> "SyncMode":
        for m in cls:
            if m.value == raw:
                return m
        # Unknown label — treat as Internal rather than crash. mod-ui has
        # added modes before; defaulting keeps the UI responsive on a
        # newer mod-ui than the device enum knows.
        logging.warning(f"Unknown syncMode label {raw!r}, defaulting to Internal")
        return cls.INTERNAL


# mod-ui REST route — see ableton-link.md §6 / mod/webserver.py.
_SYNC_ROUTE = "pedalboard/transport/set_sync_mode/"


class SyncModeSetter:
    """Off-UI-thread `POST set_sync_mode` runner.

    The 10ms UI loop must not block on HTTP (CLAUDE.md trap); this worker
    drains a one-deep slot so a rapid second request cancels a queued
    (unstarted) first. The latest-wins semantic matches mod-ui's own
    last-writer-wins for sync source.
    """

    def __init__(self, root_uri: str, post: "Callable[..., req.Response | None]") -> None:
        self._root_uri = root_uri
        self._post = post
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._pending: Optional[SyncMode] = None

    def submit(self, mode: SyncMode) -> None:
        with self._lock:
            self._pending = mode
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, daemon=True, name="set-sync-mode")
            self._thread.start()

    def join(self, timeout: Optional[float] = None) -> bool:
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def _run(self) -> None:
        while True:
            with self._lock:
                mode = self._pending
                if mode is None:
                    return
                self._pending = None
            try:
                self._post(self._root_uri + _SYNC_ROUTE + mode.wire)
            except Exception as e:
                logging.error(f"set_sync_mode POST failed: {e}")