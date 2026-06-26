"""Tuner subprocess entry point.

Usage: python -m pistomp.tuner <shm_name> <capture_port> <source_spec>
  shm_name     : POSIX SHM name created by the parent
  capture_port : JACK port, e.g. "system:capture_1"
  source_spec  : "jack", "tone:440", "sweep:440", …

Exits 0 on clean stop, 3 on error.
"""

from __future__ import annotations

import ctypes
import select
import signal
import sys
from multiprocessing.shared_memory import SharedMemory

from pistomp.tuner.engine import TunerEngine
from pistomp.tuner.source import build_source


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


_running = True


def _on_sigterm(sig, frame) -> None:
    global _running
    _running = False


def main() -> None:
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <shm_name> <capture_port> <source_spec>", file=sys.stderr)
        sys.exit(3)

    shm_name, capture_port, source_spec = sys.argv[1], sys.argv[2], sys.argv[3]
    signal.signal(signal.SIGTERM, _on_sigterm)

    shm = SharedMemory(name=shm_name, create=False)
    assert shm.buf is not None
    frame = _TunerFrame.from_buffer(shm.buf)

    source = build_source(source_spec, capture_port, name="pistomp-tuner")
    engine = TunerEngine(source)
    engine.start()

    try:
        while _running:
            rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
            if rlist:
                line = sys.stdin.readline()
                if not line or line.strip() == "stop":
                    break

            reading = engine.get_reading()
            frame.seq += 1
            if reading is None:
                frame.valid = 0
            else:
                frame.midi_note = reading.midi_note
                frame.cents = reading.cents
                frame.freq_hz = reading.freq_hz
                frame.ts = reading.ts
                frame.valid = 1
            frame.seq += 1
    finally:
        engine.stop()
        del frame
        shm.close()


if __name__ == "__main__":
    main()
