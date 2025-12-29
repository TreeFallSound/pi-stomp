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
Monitor for pedalboard changes via last.json file.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional


class PedalboardMonitor:
    """
    Because the loading_end WebSocket message does not include the
    pedalboard name, we monitor last.json for changes to get it
    (happens ~4s after loading_end message).
    """

    def __init__(self, data_dir: str):
        """
        Args:
            data_dir: Path to MOD-UI data directory (usually /home/pistomp/data)
        """
        self.last_state_file = os.path.join(data_dir, "last.json")
        self.last_state_timestamp = self._get_current_timestamp()

    def _get_current_timestamp(self) -> float:
        if Path(self.last_state_file).exists():
            return os.path.getmtime(self.last_state_file)
        return 0.0

    def check_for_change(self) -> bool:
        """
        Check if last.json has been modified since last check.

        Returns:
            True if file has changed, False otherwise
        """
        current_timestamp = self._get_current_timestamp()
        if current_timestamp != self.last_state_timestamp:
            self.last_state_timestamp = current_timestamp
            return True
        return False

    def get_current_pedalboard_bundle(self) -> Optional[str]:
        """
        Read current pedalboard bundle name from last.json.

        Returns:
            Pedalboard name, or None if file doesn't exist or can't be read
        """
        if not Path(self.last_state_file).exists():
            return None

        try:
            with open(self.last_state_file, "r") as f:
                data = json.load(f)
                return data.get("pedalboard")
        except (json.JSONDecodeError, IOError) as e:
            logging.warning(f"Failed to read {self.last_state_file}: {e}")
            return None
