"""TunerClient: spawns pistomp.tuner subprocess, reads pitch data from shared memory."""

from __future__ import annotations

import ctypes
import math

from pistomp.process_client import AudioProcessClient
from pistomp.tuner.engine import TunerReading

_NOTE_NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"]
_A4_HZ = 440.0
_A4_MIDI = 69


class _TunerFrame(ctypes.Structure):
    _fields_ = [
        ("seq", ctypes.c_uint32),
        ("valid", ctypes.c_uint32),
        ("midi_note", ctypes.c_uint32),
        ("_pad", ctypes.c_uint32),
        ("cents", ctypes.c_float),
        ("freq_hz", ctypes.c_float),
        ("ts", ctypes.c_double),
    ]


class TunerClient(AudioProcessClient):
    """Subprocess-backed tuner. get_reading() mirrors TunerEngine.get_reading()."""

    _module = "pistomp.tuner"
    _frame_type = _TunerFrame

    def start(self, capture_port: str, source_spec: str = "jack") -> None:
        self._spawn(capture_port, source_spec)

    def stop(self) -> None:
        self._terminate()

    def get_reading(self) -> TunerReading | None:
        frame = self._frame
        if not isinstance(frame, _TunerFrame):
            return None
        # Seqlock: retry if writer is mid-update (odd seq) or seq changed under us.
        # On ARM64 a torn read means one garbage frame on the display — acceptable.
        for _ in range(8):
            s1 = frame.seq
            if s1 & 1:
                continue
            if not frame.valid:
                if frame.seq == s1:
                    return None
                continue
            midi_note = frame.midi_note
            cents = frame.cents
            freq_hz = frame.freq_hz
            ts = frame.ts
            if frame.seq != s1:
                continue
            note = _NOTE_NAMES[midi_note % 12] + str((midi_note // 12) - 1)
            ideal_hz = _A4_HZ * math.pow(2.0, (midi_note - _A4_MIDI) / 12.0)
            return TunerReading(note=note, cents=cents, freq_hz=freq_hz, ideal_hz=ideal_hz, ts=ts, midi_note=midi_note)
        return None
