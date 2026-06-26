"""JACK client that plays a WAV out the FX send while recording the FX return in the same RT callback."""

from __future__ import annotations

import threading
import wave
from pathlib import Path

import numpy as np
import numpy.typing as npt

_SAMPLE_RATE = 48000
_SILENCE_PLAY_THRESHOLD = 0.1  # ≈ −20 dBFS — output must exceed this to count toward detection
_NOISE_FLOOR_THRESHOLD = 10 ** (-50 / 20)  # ≈ −50 dBFS — input high-water mark must exceed this
_NOISE_FLOOR_SETTLE_FRAMES = _SAMPLE_RATE * 4  # 4 s of loud output before we decide
_CLIP_THRESHOLD = 0.99  # float32 full-scale; any peak above → abort


class CaptureSession:
    """Plays samples out send_port while capturing return_port."""

    def __init__(
        self,
        samples: npt.NDArray[np.float32],
        send_port: str,
        return_port: str,
        *,
        name: str = "pistomp-nam",
    ) -> None:
        self._samples = samples
        self._send_port = send_port
        self._return_port = return_port
        self._client_name = name

        self._capture: npt.NDArray[np.float32] | None = None
        self._latency: int = 0  # frames; set in start() after JACK query
        self._total: int = 0  # n + latency; set in start()
        self._pos = 0
        self._loud_out_frames: int = 0
        self._in_peak_max_during_loud: float = 0.0

        self._client = None
        self._done = threading.Event()
        self._silence_abort = threading.Event()
        self._clip_abort = threading.Event()

        # Level accumulators — written by RT callback, read+reset by display thread.
        # Track max peak so short blips of audio register in the display window.
        self._acc_in: float = 0.0
        self._acc_out: float = 0.0
        self._acc_count: int = 0  # >0 means at least one callback fired

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        import jack  # type: ignore[import-untyped]

        client = jack.Client(self._client_name, no_start_server=True)
        self._client = client
        if client.samplerate != _SAMPLE_RATE:
            client.close()
            self._client = None
            raise RuntimeError(f"JACK sample rate is {client.samplerate}, expected {_SAMPLE_RATE}")

        out_port = client.outports.register("out")
        in_port = client.inports.register("in")

        # Query round-trip latency from the hardware ports so we can extend the
        # capture window and trim the result to produce an aligned WAV.
        try:
            send = client.get_port_by_name(self._send_port)
            ret = client.get_port_by_name(self._return_port)
            L = send.get_latency_range(jack.PLAYBACK)[1] + ret.get_latency_range(jack.CAPTURE)[1]
        except Exception:
            L = 0
        self._latency = L

        samples = self._samples
        n = len(samples)
        total = n + L
        self._total = total
        capture = np.zeros(total, dtype=np.float32)
        self._capture = capture

        @client.set_process_callback
        def process(frames: int) -> None:
            pos = self._pos

            # ── playback — reamp signal then silence for L extra frames ────────
            out_buf: npt.NDArray[np.float32] = out_port.get_array()
            play_remain = n - pos
            if play_remain > 0:
                take = min(frames, play_remain)
                out_buf[:take] = samples[pos : pos + take]
                if take < frames:
                    out_buf[take:] = 0.0
            else:
                out_buf[:] = 0.0

            # ── capture — record for n + L frames ─────────────────────────────
            in_buf: npt.NDArray[np.float32] = in_port.get_array()
            cap_remain = total - pos
            if cap_remain > 0:
                take = min(frames, cap_remain)
                capture[pos : pos + take] = in_buf[:take]

            # ── advance position ──────────────────────────────────────────────
            new_pos = pos + frames
            self._pos = new_pos

            # ── level checks (peak without allocating a temp array) ───────────
            out_peak = max(float(np.max(out_buf)), float(-np.min(out_buf)))
            in_peak = max(float(np.max(in_buf)), float(-np.min(in_buf)))
            if in_peak > self._acc_in:
                self._acc_in = in_peak
            if out_peak > self._acc_out:
                self._acc_out = out_peak
            self._acc_count += 1
            if in_peak >= _CLIP_THRESHOLD and not self._clip_abort.is_set():
                self._clip_abort.set()
            if out_peak >= _SILENCE_PLAY_THRESHOLD and not self._silence_abort.is_set():
                self._loud_out_frames += frames
                if in_peak > self._in_peak_max_during_loud:
                    self._in_peak_max_during_loud = in_peak
                if (
                    self._loud_out_frames >= _NOISE_FLOOR_SETTLE_FRAMES
                    and self._in_peak_max_during_loud < _NOISE_FLOOR_THRESHOLD
                ):
                    self._silence_abort.set()

            # ── EOF ───────────────────────────────────────────────────────────
            if new_pos >= total and not self._done.is_set():
                self._done.set()

        client.activate()
        client.connect(out_port, self._send_port)
        client.connect(self._return_port, in_port)

    def wait(self, timeout: float | None = None) -> bool:
        """Block until EOF or *timeout* seconds.  Returns True on EOF."""
        return self._done.wait(timeout=timeout)

    def stop(self) -> None:
        if self._client is not None:
            self._done.set()
            self._silence_abort.set()
            try:
                self._client.deactivate()
            except Exception:
                pass
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    @property
    def silence_detected(self) -> bool:
        return self._silence_abort.is_set()

    @property
    def clip_detected(self) -> bool:
        return self._clip_abort.is_set()

    def level_snapshot(self) -> tuple[float, float] | None:
        """Return (max_in_peak, max_out_peak) since last call, or None if no data yet."""
        if self._acc_count == 0:
            return None
        max_in = self._acc_in
        max_out = self._acc_out
        self._acc_in = 0.0
        self._acc_out = 0.0
        self._acc_count = 0
        return max_in, max_out

    # ── output ────────────────────────────────────────────────────────────────

    def write_wav(self, path: Path) -> None:
        """Write latency-trimmed captured audio as a 24-bit / 48 kHz / mono WAV."""
        assert self._capture is not None, "write_wav called before start()"
        L = self._latency
        end = min(self._pos, self._total)
        start = min(L, end)
        buf = self._capture[start:end]
        # float32 → int32 left-shifted by 8, then extract bytes [1,2,3] for 24-bit
        int32 = np.clip(buf * (2**31), -(2**31), 2**31 - 1).astype(np.int32)
        raw = int32.view(np.uint8).reshape(-1, 4)[:, 1:].tobytes()
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(3)
            wf.setframerate(_SAMPLE_RATE)
            wf.writeframes(raw)
