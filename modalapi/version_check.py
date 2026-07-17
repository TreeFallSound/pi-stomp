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

from __future__ import annotations

import logging
import subprocess
import threading
from typing import Optional


class DpkgDriftCheck:
    """Run `dpkg --verify pi-stomp` on a background thread."""

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._drifted: Optional[bool] = None

    def start(self) -> None:
        """Spawn the verification thread. Idempotent."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="dpkg-drift-check")
        self._thread.start()

    def join(self, timeout: Optional[float] = None) -> bool:
        """Block until the check finishes (or `timeout` elapses). Returns
        True if the check is done, False if `join` timed out."""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    @property
    def done(self) -> bool:
        return self._drifted is not None

    @property
    def drifted(self) -> bool:
        """True if drift was detected, False otherwise (including pre-start
        and on any failure — the indicator is best-effort)."""
        return bool(self._drifted)

    def _run(self) -> None:
        try:
            verify = subprocess.run(
                ["dpkg", "--verify", "pi-stomp"],
                capture_output=True,
                text=True,
                check=False,
            )
            self._drifted = bool(verify.stdout.strip() or verify.stderr.strip())
        except (FileNotFoundError, OSError) as e:
            logging.debug(f"dpkg --verify unavailable: {e}")
            self._drifted = False
        except Exception as e:
            logging.warning(f"dpkg --verify failed: {e}")
            self._drifted = False
