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

"""MetronomeClient: spawns and controls the pistomp.metronome subprocess."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

from common.util import TEARDOWN_JOIN_S


# Absolute path of the repository root, injected as PYTHONPATH so the
# subprocess imports from the same source tree as the parent process.
_SRC_ROOT = str(Path(__file__).resolve().parents[2])


class MetronomeClient:
    """Manages the metronome JACK subprocess lifecycle.

    The subprocess (``pistomp.metronome.__main__``) connects to JACK as
    ``pistomp-metronome``, registers two output ports, and writes click
    audio directly to ``system:playback_1/2``.  JACK sums multiple sources
    connected to the same playback port, so the existing
    mod-monitor→playback links are untouched.

    Control is via stdin, one ASCII command per line::

        enable   — start clicking
        disable  — silence (stay connected, write zeros)
        stop     — deactivate and exit
    """

    def __init__(self) -> None:
        self._proc: subprocess.Popen[bytes] | None = None

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self, *, enabled: bool = False) -> None:
        """Spawn the subprocess with the given initial click state."""
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (_SRC_ROOT + ":" + existing) if existing else _SRC_ROOT
        args = [sys.executable, "-m", "pistomp.metronome"]
        if enabled:
            args.append("enabled")
        self._proc = subprocess.Popen(args, stdin=subprocess.PIPE, env=env)

    def stop(self) -> None:
        """Send stop, wait, escalate to SIGTERM then SIGKILL."""
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.write(b"stop\n")
                proc.stdin.flush()
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=TEARDOWN_JOIN_S)
        except subprocess.TimeoutExpired:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=TEARDOWN_JOIN_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        self._proc = None

    # ── control ──────────────────────────────────────────────────────────────

    def set_enabled(self, enabled: bool) -> None:
        """Send ``enable`` or ``disable`` to the subprocess stdin."""
        proc = self._proc
        if proc is None or proc.stdin is None:
            return
        try:
            proc.stdin.write(b"enable\n" if enabled else b"disable\n")
            proc.stdin.flush()
        except OSError:
            pass

    def poll(self) -> int | None:
        """Return the subprocess exit code if it has exited, else None."""
        if self._proc is None:
            return None
        return self._proc.poll()
