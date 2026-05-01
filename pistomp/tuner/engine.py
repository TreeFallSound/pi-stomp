import logging
import math
import threading
import time
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from pistomp.tuner.ringbuffer import RingBuffer
from pistomp.tuner.source import AudioSource
from pistomp.tuner.yin import detect_pitch

_NOTE_NAMES = ["C", "C\u266f", "D", "D\u266f", "E", "F", "F\u266f", "G", "G\u266f", "A", "A\u266f", "B"]
_A4_HZ = 440.0
_A4_MIDI = 69


def _freq_to_note(freq_hz: float) -> tuple[str, float, float]:
    """Returns (note_name, cents_deviation, ideal_hz)."""
    midi = 12.0 * math.log2(freq_hz / _A4_HZ) + _A4_MIDI
    midi_round = round(midi)
    cents = (midi - midi_round) * 100.0
    octave = (midi_round // 12) - 1
    name = _NOTE_NAMES[midi_round % 12] + str(octave)
    ideal = _A4_HZ * (2 ** ((midi_round - _A4_MIDI) / 12.0))
    return name, cents, ideal


@dataclass(frozen=True)
class TunerReading:
    note: str
    cents: float
    freq_hz: float
    ideal_hz: float
    ts: float


class TunerEngine:
    FRAME_SIZE = 8192
    DSP_RATE_HZ = 20
    IIR_ALPHA = 0.35
    JUMP_CENTS = 600.0  # reject readings > this many cents from current estimate
    SILENCE_RMS = 0.01  # ~-40 dBFS; below this we consider input silent

    def __init__(
        self,
        source: AudioSource,
        freq_bounds: tuple[float, float] = (30.0, 1300.0),
    ) -> None:
        self._source = source
        self._freq_bounds = freq_bounds
        self._ring = RingBuffer(32768)
        self._frame: npt.NDArray[np.float32] = np.zeros(self.FRAME_SIZE, dtype=np.float32)
        self._running = False
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest: TunerReading | None = None
        self._iir_freq: float | None = None

    def start(self) -> None:
        self._running = True
        self._source.start(on_samples=self._ring.write)
        self._worker = threading.Thread(target=self._dsp_loop, daemon=True, name="tuner-dsp")
        self._worker.start()

    def stop(self) -> None:
        self._running = False
        self._source.stop()
        if self._worker is not None:
            self._worker.join(timeout=2.0)
            self._worker = None

    def _dsp_loop(self) -> None:
        interval = 1.0 / self.DSP_RATE_HZ
        while self._running:
            t0 = time.monotonic()
            self._process()
            elapsed = time.monotonic() - t0
            sleep = interval - elapsed
            if sleep > 0:
                time.sleep(sleep)

    def _process(self) -> None:
        if not self._ring.read_latest(self.FRAME_SIZE, self._frame):
            return

        rms = float(np.sqrt(np.mean(self._frame.astype(np.float64) ** 2)))
        if rms < self.SILENCE_RMS:
            self._iir_freq = None
            with self._lock:
                self._latest = None
            return

        sr = self._source.sample_rate
        lo, hi = self._freq_bounds
        freq = detect_pitch(self._frame, sr, freq_min=lo, freq_max=hi)
        if freq is None:
            return

        # Reset (don't reject) on large jumps: IIR drift could otherwise trap the
        # engine in a state where all valid readings are permanently blocked.
        if self._iir_freq is not None:
            if abs(1200.0 * math.log2(freq / self._iir_freq)) > self.JUMP_CENTS:
                self._iir_freq = None
                return

        if self._iir_freq is None:
            self._iir_freq = freq
        else:
            self._iir_freq = self.IIR_ALPHA * freq + (1.0 - self.IIR_ALPHA) * self._iir_freq

        try:
            note, cents, ideal = _freq_to_note(self._iir_freq)
        except Exception:
            logging.debug("tuner: freq_to_note failed for %s", self._iir_freq)
            return

        reading = TunerReading(
            note=note,
            cents=cents,
            freq_hz=self._iir_freq,
            ideal_hz=ideal,
            ts=time.monotonic(),
        )
        with self._lock:
            self._latest = reading

    def get_reading(self) -> TunerReading | None:
        with self._lock:
            return self._latest
