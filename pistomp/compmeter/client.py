"""GrMeterClient: spawns the compmeter subprocess, reads GR telemetry from SHM."""

from __future__ import annotations

import ctypes

from pistomp.compmeter.engine import GrReading
from pistomp.process_client import AudioProcessClient


class _GrFrame(ctypes.Structure):
    _fields_ = [
        ("seq", ctypes.c_uint32),
        ("valid", ctypes.c_uint32),
        ("in_db", ctypes.c_float),
        ("out_db", ctypes.c_float),
        ("gr_db", ctypes.c_float),
        ("_pad", ctypes.c_uint32),
        ("ts", ctypes.c_double),
    ]


class GrMeterClient(AudioProcessClient):
    """Subprocess-backed compressor GR meter. ``get_reading`` mirrors ``GrEngine``."""

    _module = "pistomp.compmeter"
    _frame_type = _GrFrame

    def start(self, in_port: str, out_port: str, makeup_db: float, source_spec: str = "jack") -> None:
        self._spawn(in_port, out_port, source_spec, f"{makeup_db}")

    def stop(self) -> None:
        self._terminate()

    def set_makeup(self, makeup_db: float) -> None:
        """Tell the subprocess the current makeup gain so its GR stays accurate."""
        proc = self._proc
        if proc is None or proc.stdin is None:
            return
        try:
            proc.stdin.write(f"makeup {makeup_db}\n".encode())
            proc.stdin.flush()
        except OSError:
            pass

    def get_reading(self) -> GrReading | None:
        frame = self._frame
        if not isinstance(frame, _GrFrame):
            return None
        # Seqlock: retry if writer is mid-update (odd seq) or seq changed under us.
        for _ in range(8):
            s1 = frame.seq
            if s1 & 1:
                continue
            valid = bool(frame.valid)
            in_db = frame.in_db
            out_db = frame.out_db
            gr_db = frame.gr_db
            ts = frame.ts
            if frame.seq != s1:
                continue
            return GrReading(in_db=in_db, out_db=out_db, gr_db=gr_db, valid=valid, ts=ts)
        return None
