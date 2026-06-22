import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from uilib import profiling
from pistomp.tuner.ringbuffer import RingBuffer
from pistomp.tuner.source import AudioSource
from pistomp.tuner.yin import YinDetector

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
    # YIN_WINDOW is the primary quality knob: how many samples the correlation
    # window sees. More samples = more periods of the fundamental = better CMND
    # curve, at the cost of slower response to note changes.
    YIN_WINDOW = 6144

    # Frame must hold YIN_WINDOW + tau_max samples. tau_max = sr / freq_min.
    # Using nominal 48 kHz / 30 Hz gives tau_max ≈ 1601.
    _FREQ_MIN_NOMINAL = 30.0
    _SR_NOMINAL = 48000
    FRAME_SIZE = YIN_WINDOW + int(_SR_NOMINAL / _FREQ_MIN_NOMINAL) + 2

    # Ring buffer: smallest power of 2 strictly greater than FRAME_SIZE.
    _RING_CAPACITY = 1 << FRAME_SIZE.bit_length()  # 8192

    DSP_RATE_HZ = 20

    # Median of the last MEDIAN_LEN raw estimates: rejects the brief octave excursions
    # YIN throws at note attacks (an IIR would smear them across wrong notes instead).
    # 5 @ 20 Hz = ~100 ms delay, survives 2 bad frames.
    # TODO: median can't catch decay-tail octave flicker (period-doubling on a fading
    # note); would need a note-lock that holds the current note against ±1200-cent jumps.
    MEDIAN_LEN = 5

    SILENCE_RMS = 0.002  # ~-54 dBFS; below this we consider input silent
    ONSET_RATIO = 4.0  # RMS jump factor that signals a new note being plucked (~12 dB)
    ONSET_HOLDOFF_FRAMES = 1  # frames to skip after onset (rejects attack transient)

    def __init__(
        self,
        source: AudioSource,
        freq_bounds: tuple[float, float] = (30.0, 1300.0),
    ) -> None:
        self._source = source
        self._freq_bounds = freq_bounds
        self._ring = RingBuffer(self._RING_CAPACITY)
        self._frame: npt.NDArray[np.float32] = np.zeros(self.FRAME_SIZE, dtype=np.float32)
        self._running = False
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest: TunerReading | None = None
        self._freq_history: deque[float] = deque(maxlen=self.MEDIAN_LEN)
        self._prev_rms: float = 0.0
        self._onset_holdoff: int = 0
        self._detector: YinDetector | None = None

    def start(self) -> None:
        self._running = True
        self._source.start(on_samples=self._ring.write)
        lo, hi = self._freq_bounds
        self._detector = YinDetector(
            self.FRAME_SIZE, self._source.sample_rate,
            freq_min=lo, freq_max=hi, window=self.YIN_WINDOW,
        )
        self._worker = threading.Thread(target=self._dsp_loop, daemon=True, name="tuner-dsp")
        self._worker.start()

    def stop(self) -> None:
        self._running = False
        self._source.stop()
        if self._worker is not None:
            self._worker.join(timeout=2.0)
            self._worker = None
        self._detector = None

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

        with profiling.measure("rms", bin_override="dsp"):
            rms = float(np.sqrt(np.mean(self._frame ** 2)))

        if rms < self.SILENCE_RMS:
            self._freq_history.clear()
            self._onset_holdoff = 0
            self._prev_rms = rms
            with self._lock:
                self._latest = None
            return

        # Amplitude onset: a sudden RMS jump means the player plucked a new note.
        # Reset IIR immediately and skip ONSET_HOLDOFF_FRAMES to let the transient pass.
        if rms > self._prev_rms * self.ONSET_RATIO:
            self._freq_history.clear()
            self._onset_holdoff = self.ONSET_HOLDOFF_FRAMES
            with self._lock:
                self._latest = None
        self._prev_rms = rms

        if self._onset_holdoff > 0:
            self._onset_holdoff -= 1
            return

        with profiling.measure("detect_pitch(YIN)", bin_override="dsp"):
            assert self._detector is not None
            estimate = self._detector.detect(self._frame)
        if estimate is None:
            return

        self._freq_history.append(estimate.freq)
        freq = float(np.median(self._freq_history))

        try:
            note, cents, ideal = _freq_to_note(freq)
        except Exception:
            logging.debug("tuner: freq_to_note failed for %s", freq)
            return

        reading = TunerReading(
            note=note,
            cents=cents,
            freq_hz=freq,
            ideal_hz=ideal,
            ts=time.monotonic(),
        )
        with self._lock:
            self._latest = reading

    def get_reading(self) -> TunerReading | None:
        with self._lock:
            return self._latest
