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

"""
Monitors a file for modification-time changes.

Used to detect when MOD-UI writes last.json (pedalboard change) or
banks.json (bank list change) without polling the WebSocket.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional


class FileChangeMonitor:
    """Detects when a file has been modified since the last check."""

    def __init__(self, file_path: str):
        self.path = file_path
        self._last_timestamp = self._current_timestamp()

    def _current_timestamp(self) -> float:
        p = Path(self.path)
        return os.path.getmtime(self.path) if p.exists() else 0.0

    def check_for_change(self) -> bool:
        """Return True (and update baseline) if the file was modified since last call."""
        ts = self._current_timestamp()
        if ts != self._last_timestamp:
            self._last_timestamp = ts
            return True
        return False


def read_pedalboard_bundle(last_json_path: str) -> Optional[str]:
    """Read the current pedalboard bundle name from last.json."""
    if not Path(last_json_path).exists():
        return None
    try:
        with open(last_json_path, "r") as f:
            return json.load(f).get("pedalboard")
    except (json.JSONDecodeError, IOError) as e:
        logging.warning(f"Failed to read {last_json_path}: {e}")
        return None
