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

_ERROR_MSG = "Sync error — see logs: journalctl -u mod-ala-pi-stomp"
_CLONE_ERROR_MSG = "Clone failed — see logs: journalctl -u mod-ala-pi-stomp"


@dataclass
class SyncResult:
    status: Literal["up_to_date", "applied", "conflicts", "network_error",
                    "error", "remote_conflict", "cloned"]
    count: int = 0
    conflicts: list = field(default_factory=list)
    message: str = ""


class PedalboardSync:
    _SCRIPT = "util/sync-pedalboards.sh"

    def __init__(
        self,
        pedalboards_dir: Path | None = None,
        homedir: Path | None = None,
        username: str | None = None,
    ):
        if pedalboards_dir is None:
            pedalboards_dir = Path.home() / ".pedalboards"
        self.pedalboards_dir = Path(pedalboards_dir)
        if homedir is None:
            homedir = Path(__file__).parent.parent
        self.script = str(Path(homedir) / self._SCRIPT)
        self.username = username

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self) -> SyncResult:
        return self._run(dry_run=True)

    def apply(self) -> SyncResult:
        return self._run(dry_run=False)

    def configure_remote(self, url: str) -> SyncResult:
        """Ensure the pedalboards repo exists and points to url, then sync.

        Safe rules:
        - No repo at all (or empty dir) → clone.
        - Dir exists, non-empty, no .git → refuse rather than clobber.
        - Remote already matches → sync normally.
        - Remote differs, no local commits not on origin → switch + sync.
        - Remote differs, local commits exist → block and notify user.
        """
        if not (self.pedalboards_dir / ".git").exists():
            return self._clone(url)

        if self._get_remote() == url:
            return self.apply()

        if self._has_local_commits():
            return SyncResult(
                status="remote_conflict",
                message="Remote mismatch: local commits not on origin. Resolve via SSH then sync.",
            )

        self._set_remote(url)
        return self.apply()

    # ------------------------------------------------------------------
    # Remote / repo helpers
    # ------------------------------------------------------------------

    def _clone(self, url: str) -> SyncResult:
        if self.pedalboards_dir.exists() and any(self.pedalboards_dir.iterdir()):
            return SyncResult(
                status="error",
                message="Cannot clone: directory exists and is not empty. Resolve via SSH.",
            )

        cmd = ["git", "clone", url, str(self.pedalboards_dir)]
        if self.username:
            cmd = ["sudo", "-u", self.username] + cmd
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                return SyncResult(
                    status="cloned",
                    message="Pedalboards cloned — restart sound engine to load",
                )
            logging.error("clone failed: %s", result.stderr)
            return SyncResult(status="error", message=_CLONE_ERROR_MSG)
        except subprocess.TimeoutExpired:
            logging.error("clone: timeout")
            return SyncResult(status="error", message=_CLONE_ERROR_MSG)
        except Exception as e:
            logging.error("clone: %s", e)
            return SyncResult(status="error", message=_CLONE_ERROR_MSG)

    def _get_remote(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.pedalboards_dir), "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def _set_remote(self, url: str) -> None:
        cmd = ["git", "-C", str(self.pedalboards_dir), "remote", "set-url", "origin", url]
        if self.username:
            cmd = ["sudo", "-u", self.username] + cmd
        subprocess.run(cmd, capture_output=True, timeout=10)

    def _has_local_commits(self) -> bool:
        """True if HEAD has commits not present on any origin branch."""
        try:
            result = subprocess.run(
                ["git", "-C", str(self.pedalboards_dir),
                 "rev-list", "HEAD", "--not", "--remotes=origin", "--count"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode != 0 or int(result.stdout.strip() or "1") > 0
        except Exception:
            return True  # conservative: assume diverged

    # ------------------------------------------------------------------
    # Script runner
    # ------------------------------------------------------------------

    def _run(self, dry_run: bool) -> SyncResult:
        script_args = [self.script, str(self.pedalboards_dir)]
        if dry_run:
            script_args.insert(1, "--dry-run")

        cmd = (["sudo", "-u", self.username] + script_args) if self.username else script_args

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            logging.error("sync-pedalboards: timeout")
            return SyncResult(status="error", message="Sync timeout")
        except Exception as e:
            logging.error("sync-pedalboards: %s", e)
            return SyncResult(status="error", message=_ERROR_MSG)

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
            conflicts = [line for line in lines if not line.startswith("Conflicts:")]
            logging.warning("sync-pedalboards conflicts: %s", conflicts)
            return SyncResult(status="conflicts", conflicts=conflicts, message="Sync aborted: conflicts")
        logging.error("sync-pedalboards error (exit %d): %s", code, stdout)
        return SyncResult(status="error", message=_ERROR_MSG)
