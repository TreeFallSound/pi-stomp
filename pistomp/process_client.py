"""Base class for pi-stomp audio subprocess clients.

Manages a single Python subprocess (-m module) backed by shared memory for
high-frequency telemetry (RT→main) and a stdin pipe for low-frequency control
(main→subprocess).
"""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
from pathlib import Path
from multiprocessing.shared_memory import SharedMemory

# Root of the pi-stomp source tree (two levels up from pistomp/process_client.py).
# Passed as PYTHONPATH to subprocesses so they load from the source tree like the
# main process does (which gets it via sys.path[0] from the script invocation).
_SRC_ROOT = str(Path(__file__).resolve().parents[1])


def attach_shm(name: str) -> SharedMemory:
    """Attach to a SHM segment created by the parent's ``AudioProcessClient``.

    ``SharedMemory.__init__`` registers with *this process's own*
    resource_tracker even in attach mode, but only the parent (which alone
    calls ``unlink()`` in ``_terminate()``) owns cleanup. Left registered, the
    subprocess's tracker treats the segment as leaked and races the parent to
    unlink it at exit (https://bugs.python.org/issue38119) — so drop it here.
    """
    from multiprocessing import resource_tracker

    shm = SharedMemory(name=name, create=False)
    resource_tracker.unregister(shm._name, "shared_memory")  # pyright: ignore[reportPrivateUsage]
    return shm


class AudioProcessClient:
    """Spawn, communicate with, and kill an audio subprocess.

    Subclasses declare:
        _module     : str                      e.g. "pistomp.tuner"
        _frame_type : type[ctypes.Structure]   SHM layout
    """

    _module: str
    _frame_type: type[ctypes.Structure]

    def __init__(self) -> None:
        self._proc: subprocess.Popen[bytes] | None = None
        self._shm: SharedMemory | None = None
        self._frame: ctypes.Structure | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def _spawn(self, *extra_args: str) -> None:
        size = ctypes.sizeof(self._frame_type)
        shm = SharedMemory(create=True, size=max(size, 1))
        self._shm = shm
        assert shm.buf is not None
        self._frame = self._frame_type.from_buffer(shm.buf)
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (_SRC_ROOT + ":" + existing) if existing else _SRC_ROOT
        self._proc = subprocess.Popen(
            [sys.executable, "-m", self._module, shm.name, *extra_args],
            stdin=subprocess.PIPE,
            env=env,
        )

    def _terminate(self, timeout: float = 3.0) -> int | None:
        """Send stop, wait, escalate to SIGTERM then SIGKILL. Returns exit code."""
        proc = self._proc
        if proc is None:
            return None
        try:
            if proc.stdin:
                proc.stdin.write(b"stop\n")
                proc.stdin.flush()
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        rc = proc.returncode
        self._proc = None
        self._frame = None
        if self._shm is not None:
            try:
                self._shm.close()
                self._shm.unlink()
            except Exception:
                pass
            self._shm = None
        return rc

    def poll(self) -> int | None:
        """Return subprocess exit code, or None if still running."""
        if self._proc is None:
            return None
        return self._proc.poll()

    def wait(self, timeout: float | None = None) -> bool:
        """Block until subprocess exits. Returns True if it exited."""
        if self._proc is None:
            return True
        try:
            self._proc.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False
