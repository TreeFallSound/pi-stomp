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
Local-monitor mute: disconnects mod-monitor from system:playback so the pi's
audio out goes silent. Other JACK clients (e.g. mod-peakmeter, netJACK2) still
receive the signal.
"""

import subprocess
from typing import List, Tuple

_PAIRS: List[Tuple[str, str]] = [
    ("mod-monitor:out_1", "system:playback_1"),
    ("mod-monitor:out_2", "system:playback_2"),
]


class JackMute:
    """Reads/sets the local-monitor connection state via jack_lsp/connect/disconnect."""

    def is_muted(self) -> bool:
        """
        True if the primary mod-monitor → system:playback link is absent.
        If `jack_lsp` fails (JACK down), we report not-muted.
        """
        try:
            out = subprocess.check_output(
                ["jack_lsp", "-c", "mod-monitor:out_1"], stderr=subprocess.DEVNULL, text=True, timeout=2.0
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
        return "system:playback_1" not in out

    def mute(self) -> None:
        for src, dst in _PAIRS:
            self._run("jack_disconnect", src, dst)

    def unmute(self) -> None:
        for src, dst in _PAIRS:
            self._run("jack_connect", src, dst)

    @staticmethod
    def _run(tool: str, src: str, dst: str) -> None:
        try:
            subprocess.call([tool, src, dst], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0)
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
