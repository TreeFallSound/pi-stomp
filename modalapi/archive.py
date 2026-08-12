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

"""Backup/restore archiving on a worker thread, with progress the UI can poll.

zip and unzip both name each entry as they finish it. Weighting those lines by
the entry's uncompressed size gives a bar that tracks wall-clock rather than
file count — 306 NAM models at ~295KB each dominate the run, while hundreds of
small .ttl files would otherwise sprint the bar to nowhere.
"""

import enum
import logging
import os
import re
import signal
import subprocess
import threading
import zipfile

# "  adding: path/to/file (deflated 12%)" — the path may contain spaces and
# parens, so anchor on the trailing method/ratio rather than splitting.
_ZIP_ENTRY = re.compile(r"^\s*(?:adding|updating):\s+(.*?)\s+\((?:stored|deflated)\s+\d+%\)\s*$")
_UNZIP_ENTRY = re.compile(r"^\s*(?:extracting|inflating|linking|creating):\s+(.+?)\s*$")


class JobState(enum.Enum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ArchiveJob:
    """Runs one archiving subprocess off of the UI thread. Poll progress()/state
    from the main thread; nothing here touches the LCD."""

    def __init__(self, argv: list[str], weights: dict[str, int], entry_re: re.Pattern[str]) -> None:
        self._argv = argv
        self._weights = weights
        self._entry_re = entry_re
        self._total = sum(weights.values()) or 1
        self._done = 0
        self._entry = ""
        self._lock = threading.Lock()
        self._state = JobState.RUNNING
        self._error = ""
        self._proc: subprocess.Popen[str] | None = None
        self._cancelled = False
        self._thread = threading.Thread(target=self._run, daemon=True, name="archive-job")
        self._thread.start()

    @staticmethod
    def backup(script: str, dest: str, src_dir: str) -> "ArchiveJob":
        weights = {}
        for root, dirs, files in os.walk(src_dir):
            if os.path.relpath(root, src_dir) == ".":
                dirs[:] = [d for d in dirs if d != ".lv2"]
            for name in files:
                path = os.path.join(root, name)
                rel = os.path.relpath(path, src_dir)
                try:
                    weights[rel] = os.stat(path, follow_symlinks=True).st_size
                except OSError:
                    weights[rel] = 0
        return ArchiveJob([script, dest, src_dir], weights, _ZIP_ENTRY)

    @staticmethod
    def restore(script: str, username: str, archive: str, target_dir: str) -> "ArchiveJob":
        with zipfile.ZipFile(archive) as zf:
            weights = {i.filename: i.file_size for i in zf.infolist() if not i.is_dir()}
        return ArchiveJob(["sudo", "-u", username, script, archive, target_dir], weights, _UNZIP_ENTRY)

    def progress(self) -> float:
        with self._lock:
            return min(1.0, self._done / self._total)

    @property
    def current_entry(self) -> str:
        with self._lock:
            return self._entry

    @property
    def done_bytes(self) -> int:
        with self._lock:
            return min(self._done, self._total)

    @property
    def total_bytes(self) -> int:
        return self._total

    @property
    def state(self) -> JobState:
        with self._lock:
            return self._state

    @property
    def error(self) -> str:
        with self._lock:
            return self._error

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        # The script is a bash parent of zip; signal the group or only bash dies.
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError) as e:
            logging.warning("archive cancel: %s", e)

    def _run(self) -> None:
        try:
            proc = subprocess.Popen(
                self._argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
        except OSError as e:
            with self._lock:
                self._state = JobState.FAILED
                self._error = str(e)
            return

        with self._lock:
            self._proc = proc

        tail: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            m = self._entry_re.match(line)
            if m is None:
                tail.append(line.rstrip())
                del tail[:-8]
                continue
            name = m.group(1)
            weight = self._weights.get(name)
            if weight is None:
                continue
            with self._lock:
                self._done += weight
                self._entry = name

        rc = proc.wait()
        with self._lock:
            if self._cancelled:
                self._state = JobState.CANCELLED
            elif rc == 0:
                self._state = JobState.DONE
                self._done = self._total
            else:
                self._state = JobState.FAILED
                self._error = "\n".join(tail) or f"exited {rc}"
