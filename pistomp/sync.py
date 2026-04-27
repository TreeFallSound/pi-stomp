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
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class SyncResult:
    status: Literal["up_to_date", "applied", "conflicts", "network_error", "error"]
    count: int = 0
    conflicts: list = field(default_factory=list)
    message: str = ""


class PedalboardSync:
    _SCRIPT = "util/sync-pedalboards.sh"

    def __init__(
        self,
        pedalboards_dir: Path = None,
        homedir: Path = None,
        username: str = None,
    ):
        if pedalboards_dir is None:
            pedalboards_dir = Path.home() / ".pedalboards"
        self.pedalboards_dir = Path(pedalboards_dir)
        if homedir is None:
            homedir = Path(__file__).parent.parent
        self.script = str(Path(homedir) / self._SCRIPT)
        self.username = username

    def check(self) -> SyncResult:
        return self._run(dry_run=True)

    def apply(self) -> SyncResult:
        return self._run(dry_run=False)

    def _run(self, dry_run: bool) -> SyncResult:
        script_args = [self.script, str(self.pedalboards_dir)]
        if dry_run:
            script_args.insert(1, "--dry-run")

        if self.username:
            cmd = ["sudo", "-u", self.username] + script_args
        else:
            cmd = script_args

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            logging.error("sync-pedalboards: timeout")
            return SyncResult(status="error", message="Sync timeout")
        except Exception as e:
            logging.error("sync-pedalboards: %s", e)
            return SyncResult(status="error", message="Sync error — see logs")

        return self._parse(result.returncode, result.stdout.strip())

    def _parse(self, code: int, stdout: str) -> SyncResult:
        if code == 0:
            if "Already up to date" in stdout:
                return SyncResult(status="up_to_date", message="Up to date")
            m = re.search(r"(\d+) update", stdout)
            count = int(m.group(1)) if m else 0
            return SyncResult(status="applied", count=count, message=f"{count} update(s) applied")
        if code == 2:
            logging.error("sync-pedalboards network error: %s", stdout)
            return SyncResult(status="network_error", message="Sync failed: no network")
        if code == 3:
            lines = stdout.splitlines()
            conflicts = [l for l in lines if not l.startswith("Conflicts:")]
            logging.warning("sync-pedalboards conflicts: %s", conflicts)
            return SyncResult(status="conflicts", conflicts=conflicts, message="Sync aborted: conflicts")
        logging.error("sync-pedalboards error (exit %d): %s", code, stdout)
        return SyncResult(status="error", message="Sync error — see logs")
