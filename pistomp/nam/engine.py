from __future__ import annotations

import logging
import math
import threading
from enum import Enum, auto
from pathlib import Path

from pistomp.nam import routing
from pistomp.nam.client import NamCaptureClient
from pistomp.nam.wavio import wav_duration

_REAMP_WAV = Path(__file__).resolve().parents[2] / "setup" / "nam" / "T3K-sweep-v3.wav"

# Exit codes from the NAM subprocess
_EXIT_DONE = 0
_EXIT_SILENCE = 1
_EXIT_CLIP = 2
_EXIT_ABORTED = 5


class CaptureState(Enum):
    IDLE = auto()
    CAPTURING = auto()
    DONE = auto()
    FAILED = auto()
    ABORTED = auto()


class NamCaptureEngine:
    """Orchestrates a single FX-loop NAM recording session via a subprocess."""

    def __init__(
        self,
        output_dir: Path | str,
        reamp_wav: Path | str = _REAMP_WAV,
        send_port: str = routing.FX_SEND_PORT,
        return_port: str = routing.FX_RETURN_PORT,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._reamp_wav = Path(reamp_wav)
        self._send_port = send_port
        self._return_port = return_port

        self._state = CaptureState.IDLE
        self._progress: float = 0.0
        self._error: str | None = None
        self._output_path: Path | None = None
        self._pending_path: Path | None = None
        self._thread: threading.Thread | None = None
        self._abort = threading.Event()
        self._lock = threading.Lock()
        self._client: NamCaptureClient | None = None

    # ── public API ────────────────────────────────────────────────────────────

    @property
    def state(self) -> CaptureState:
        with self._lock:
            return self._state

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    @property
    def output_path(self) -> Path | None:
        with self._lock:
            return self._output_path

    @property
    def pending_path(self) -> Path | None:
        with self._lock:
            return self._pending_path

    def progress(self) -> float:
        with self._lock:
            return self._progress

    def start(self, name: str) -> None:
        with self._lock:
            if self._state == CaptureState.CAPTURING:
                return
            self._state = CaptureState.CAPTURING
            self._progress = 0.0
            self._error = None
            self._output_path = None
            self._pending_path = None
            self._abort.clear()

        self._thread = threading.Thread(target=self._run, args=(name,), daemon=True, name="nam-capture")
        self._thread.start()

    def level_snapshot_db(self) -> tuple[float, float] | None:
        with self._lock:
            client = self._client
        if client is None:
            return None
        snap = client.level_snapshot()
        if snap is None:
            return None
        in_peak, out_peak = snap

        def to_db(p: float) -> float:
            return 20.0 * math.log10(max(p, 1e-10))

        return to_db(in_peak), to_db(out_peak)

    def stop(self) -> None:
        self._abort.set()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            self._thread = None

    def reset(self) -> None:
        with self._lock:
            if self._state not in (CaptureState.DONE, CaptureState.FAILED, CaptureState.ABORTED):
                return
            self._state = CaptureState.IDLE
            self._error = None
            self._output_path = None
            self._pending_path = None
            self._progress = 0.0

    # ── internal ──────────────────────────────────────────────────────────────

    def _run(self, name: str) -> None:
        saved: routing.Saved | None = None
        client: NamCaptureClient | None = None

        try:
            if not self._reamp_wav.exists():
                raise FileNotFoundError(
                    f"Reamp WAV not found: {self._reamp_wav}\n"
                    "Download T3K-sweep-v3.wav from the NAM trainer and place it at "
                    f"{self._reamp_wav}"
                )

            duration = wav_duration(self._reamp_wav)

            if self._abort.is_set():
                self._set_state(CaptureState.ABORTED)
                return

            saved = routing.snapshot(self._send_port, self._return_port)
            routing.clear(self._send_port, self._return_port)
            routing.connect_monitor()

            if self._abort.is_set():
                routing.restore(saved)
                saved = None
                self._set_state(CaptureState.ABORTED)
                return

            out_wav = self._resolve_output_path(name)
            with self._lock:
                self._pending_path = out_wav

            client = NamCaptureClient()
            client.start(
                str(self._reamp_wav),
                str(out_wav),
                self._send_port,
                self._return_port,
            )
            with self._lock:
                self._client = client

            import time

            t0 = time.monotonic()

            while True:
                if self._abort.is_set():
                    client.stop()
                    client.wait(timeout=10.0)
                    with self._lock:
                        self._client = None
                        self._output_path = out_wav
                        self._state = CaptureState.ABORTED
                    return

                rc = client.poll()
                if rc is not None:
                    with self._lock:
                        self._client = None
                    self._apply_exit_code(rc, out_wav)
                    return

                elapsed = time.monotonic() - t0
                with self._lock:
                    self._progress = min(elapsed / duration, 0.99)

                time.sleep(0.1)

        except Exception as exc:
            logging.error("NAM capture failed: %s", exc, exc_info=True)
            with self._lock:
                self._client = None
                self._error = str(exc)
                self._state = CaptureState.FAILED

        finally:
            if client is not None and client.poll() is None:
                client.stop()
            with self._lock:
                self._client = None
            if saved is not None:
                try:
                    routing.restore(saved)
                except Exception as exc:
                    logging.error("NAM routing restore failed: %s", exc)

    def _apply_exit_code(self, rc: int, out_wav: Path) -> None:
        if rc == _EXIT_DONE:
            with self._lock:
                self._output_path = out_wav
                self._progress = 1.0
                self._state = CaptureState.DONE
        elif rc == _EXIT_SILENCE:
            with self._lock:
                self._error = "No audio detected"
                self._state = CaptureState.FAILED
        elif rc == _EXIT_CLIP:
            with self._lock:
                self._error = "Reduce amp output"
                self._state = CaptureState.FAILED
        elif rc == _EXIT_ABORTED:
            with self._lock:
                self._output_path = out_wav
                self._state = CaptureState.ABORTED
        else:
            with self._lock:
                self._error = "Capture failed"
                self._state = CaptureState.FAILED

    def _resolve_output_path(self, name: str) -> Path:
        safe = (name.strip() or "capture").replace("/", "_").replace("\\", "_")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        out_wav = self._output_dir / f"{safe}.wav"
        n = 2
        while out_wav.exists():
            out_wav = self._output_dir / f"{safe}-{n}.wav"
            n += 1
        return out_wav

    def _set_state(self, state: CaptureState) -> None:
        with self._lock:
            self._state = state
