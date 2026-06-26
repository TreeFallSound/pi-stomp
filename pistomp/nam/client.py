"""NamCaptureClient: spawns pistomp.nam subprocess, reads level data from shared memory."""

from __future__ import annotations

import ctypes

from pistomp.process_client import AudioProcessClient


class _NamFrame(ctypes.Structure):
    _fields_ = [
        ("seq", ctypes.c_uint32),
        ("valid", ctypes.c_uint32),
        ("in_peak", ctypes.c_float),
        ("out_peak", ctypes.c_float),
    ]


class NamCaptureClient(AudioProcessClient):
    """Subprocess-backed NAM capture session.

    The subprocess handles JACK client creation, audio I/O, WAV writing, and exits with:
        0 = done (WAV written)
        1 = silence detected
        2 = clip detected
        3 = error / exception
        5 = aborted (partial WAV written)
    """

    _module = "pistomp.nam"
    _frame_type = _NamFrame

    def start(self, reamp_wav: str, output_path: str, send_port: str, return_port: str) -> None:
        self._spawn(reamp_wav, output_path, send_port, return_port)

    def stop(self) -> None:
        self._terminate(timeout=10.0)

    def level_snapshot(self) -> tuple[float, float] | None:
        """Return (in_peak, out_peak) max since last subprocess display-thread write, or None."""
        frame = self._frame
        if not isinstance(frame, _NamFrame):
            return None
        for _ in range(8):
            s1 = frame.seq
            if s1 & 1:
                continue
            if not frame.valid:
                if frame.seq == s1:
                    return None
                continue
            in_peak = frame.in_peak
            out_peak = frame.out_peak
            if frame.seq == s1:
                return in_peak, out_peak
        return None
