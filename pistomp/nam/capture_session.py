"""JACK client that plays a WAV out the FX send while recording the FX return in the same RT callback."""

from __future__ import annotations

import threading
import wave
from pathlib import Path

import numpy as np
import numpy.typing as npt

_SAMPLE_RATE = 48000
_CLIP_THRESHOLD = 0.99  # float32 full-scale; any peak above → abort
_SILENCE_RATIO_SQ = 10 ** (-15 / 10)  # input RMS this far (−15 dB) below latency-aligned output RMS = a silent period
_SILENCE_ABORT_FRAMES = _SAMPLE_RATE * 2  # 2 s of accumulated silent periods → abort
# FIXME: need to expire the silent frames counter after a few seconds of non-silent input, otherwise a single blip of silence can trigger an abort after a long capture.

"""
The red LED means the audio input signal level — measured by the ADC before any ALSA/JACK gain is applied — has exceeded -15 dBV adjusted for input gain (analogVU.py:83).

Specifically:

- The MCP3008 ADC reads the raw input signal at 10ms intervals
- Each reading is reflected around the DC baseline (so positive and negative swings are treated equivalently: abs(baseline - value) + baseline)
- A short 4-sample rolling average (~40ms) is compared against three thresholds, all computed as baseline + amplitude_at_threshold_db:

┌───────┬────────┬──────────────────────┐
│ State │ Color  │      Threshold       │
├───────┼────────┼──────────────────────┤
│ SIG   │ Green  │ −39 dBV − input_gain │
├───────┼────────┼──────────────────────┤
│ WARN  │ Orange │ −20 dBV − input_gain │
├───────┼────────┼──────────────────────┤
│ CLIP  │ Red    │ −15 dBV − input_gain │
└───────┴────────┴──────────────────────┘

Because the ADC sits upstream of the ALSA capture gain stage, the thresholds shift inversely with input_gain — if you crank up the capture volume, the clip threshold moves lower (less ADC amplitude needed to trigger red), reflecting that the downstream analog stage will clip at a lower input level.

So red = the input signal is hot enough that it's likely clipping the analog input stage of the audio card, not just being loud in software.

The input_gain side is not manually calibrated — it's read from the ALSA capture volume and baked into the threshold math automatically via recalibrate_gain(). The dB thresholds themselves (-39, -20, -15) are hardcoded.

What we detect now:
- _CLIP_THRESHOLD = 0.99 in capture_session.py — digital full-scale in JACK float32. Only catches true digital clipping.

What we're missing:
- The AnalogVU hardware objects already model the audio card's analog input stage clipping at -15 dBV x input_gain. This is exactly the threshold where the circuit is distorting the signal before the ADC even converts it. The current capture process never consults this.

TODO: Proposed approach:

1. Add abort_with_error(msg: str) to NamCaptureEngine — sets FAILED with a custom message without going through the subprocess exit code path.
2. In NamCapturePanel.tick() during CAPTURING state, check self._handler.hardware.indicators for any AnalogVU in VuState.CLIP state, sustained for ~5 consecutive ticks (~50ms) to avoid aborting on a transient.
3. Call engine.abort_with_error("Analog clipping: lower amp output") when triggered.

This is better than lowering _CLIP_THRESHOLD in the session because it uses your already-calibrated per-gain-setting hardware thresholds rather than a crude dBFS approximation. It also produces a more actionable error message.

One question before implementing: the sustained-clip window (50ms) — do you want that, or should any single CLIP reading during capture abort immediately? Since the capture is measuring a sweep signal that naturally has quiet periods, a transient hit at the loudest part of the sweep seems like a legitimate abort condition, not just noise.
"""


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
        self._silent_frames: int = 0  # accumulated frames where input sat ≥15 dB below output; never cleared

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

            # ── silence — input RMS persistently far below latency-aligned output RMS ──
            # The input this callback was produced by output sent L frames ago; compare
            # against that slice (zeros outside the played range = real output silence).
            # Squared domain avoids sqrt: in_ss < out_ss·r²  ⟺  in_rms < out_rms·r (same /frames).
            if not self._silence_abort.is_set():
                lo = max(pos - self._latency, 0)
                hi = min(pos - self._latency + frames, n)
                out_seg = samples[lo:hi]
                out_ss = float(np.dot(out_seg, out_seg)) if hi > lo else 0.0
                in_ss = float(np.dot(in_buf, in_buf))
                if in_ss < out_ss * _SILENCE_RATIO_SQ:
                    self._silent_frames += frames
                    if self._silent_frames >= _SILENCE_ABORT_FRAMES:
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
