"""NAM capture subprocess entry point.

Usage: python -m pistomp.nam <shm_name> <reamp_wav> <output_path> <send_port> <return_port>

Exit codes:
    0  done, WAV written to output_path
    1  silence detected (no WAV written)
    2  clip detected (no WAV written)
    3  error / exception (no WAV written)
    5  aborted via stdin "stop" or SIGTERM (partial WAV written)
"""

from __future__ import annotations

import ctypes
import select
import signal
import sys
import threading
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path

from pistomp.nam.capture_session import CaptureSession
from pistomp.nam.wavio import load_wav_float32


class _NamFrame(ctypes.Structure):
    _fields_ = [
        ("seq", ctypes.c_uint32),
        ("valid", ctypes.c_uint32),
        ("in_peak", ctypes.c_float),
        ("out_peak", ctypes.c_float),
    ]


_abort = threading.Event()


def _on_sigterm(sig, frame_) -> None:
    _abort.set()


def _level_writer(session: CaptureSession, frame: _NamFrame, stop: threading.Event) -> None:
    """Non-RT thread: reads RT accumulators, writes to SHM at ~10 Hz."""
    while not stop.wait(timeout=0.1):
        snap = session.level_snapshot()
        if snap is None:
            continue
        in_peak, out_peak = snap
        frame.seq += 1
        frame.in_peak = in_peak
        frame.out_peak = out_peak
        frame.valid = 1
        frame.seq += 1


def main() -> None:
    if len(sys.argv) < 6:
        print(
            f"Usage: {sys.argv[0]} <shm_name> <reamp_wav> <output_path> <send_port> <return_port>",
            file=sys.stderr,
        )
        sys.exit(3)

    shm_name = sys.argv[1]
    reamp_wav = sys.argv[2]
    output_path = Path(sys.argv[3])
    send_port = sys.argv[4]
    return_port = sys.argv[5]

    signal.signal(signal.SIGTERM, _on_sigterm)

    shm = SharedMemory(name=shm_name, create=False)
    assert shm.buf is not None
    frame = _NamFrame.from_buffer(shm.buf)
    exit_code = 3

    try:
        try:
            samples = load_wav_float32(reamp_wav)
        except Exception as exc:
            print(f"Failed to load reamp WAV: {exc}", file=sys.stderr)
            sys.exit(3)

        session = CaptureSession(samples, send_port, return_port)
        stop_writer = threading.Event()
        writer = threading.Thread(target=_level_writer, args=(session, frame, stop_writer), daemon=True)

        try:
            session.start()
            writer.start()

            while not session.wait(timeout=0.1):
                rlist, _, _ = select.select([sys.stdin], [], [], 0.0)
                if rlist:
                    line = sys.stdin.readline()
                    if not line or line.strip() == "stop":
                        _abort.set()

                if _abort.is_set():
                    session.stop()
                    stop_writer.set()
                    writer.join(timeout=2.0)
                    session.write_wav(output_path)
                    exit_code = 5
                    return

                if session.clip_detected:
                    session.stop()
                    stop_writer.set()
                    writer.join(timeout=2.0)
                    exit_code = 2
                    return

                if session.silence_detected:
                    session.stop()
                    stop_writer.set()
                    writer.join(timeout=2.0)
                    exit_code = 1
                    return

            stop_writer.set()
            writer.join(timeout=2.0)
            session.write_wav(output_path)
            exit_code = 0

        except Exception as exc:
            print(f"NAM capture error: {exc}", file=sys.stderr)
            stop_writer.set()
            try:
                session.stop()
            except Exception:
                pass

    finally:
        del frame
        shm.close()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
