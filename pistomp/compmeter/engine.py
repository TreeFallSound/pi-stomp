"""GR-meter DSP: envelope-follow the in/out blocks and derive gain reduction."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import numpy.typing as npt

from pistomp.compmeter.source import PairedAudioSource

_SILENCE_DB = -60.0  # below this input level, GR is meaningless
_MIN_LIN = 1e-9  # floor before log10


@dataclass(frozen=True)
class GrReading:
    in_db: float
    out_db: float
    gr_db: float
    valid: bool
    ts: float


class GrBackend(Protocol):
    """Shared interface for the in-process engine and the subprocess client."""

    def get_reading(self) -> GrReading | None: ...
    def stop(self) -> None: ...


def _to_db(lin: float) -> float:
    return 20.0 * math.log10(max(lin, _MIN_LIN))


class GrEngine:
    """Envelope-follows paired input/output audio and derives gain reduction.

    ``GR ≈ in_db + makeup_db - out_db`` (clamped >= 0): the compressor's output is
    ``input · comp_gain · makeup``, so subtracting the known makeup isolates the
    downward gain the compressor applied. A one-pole envelope on each block
    smooths the block-RMS so the displayed meter does not flicker.
    """

    # Envelope smoothing coefficient per block (~fast attack, matches metering).
    _ENV_COEFF = 0.3

    def __init__(self, source: PairedAudioSource, makeup_db: float = 0.0) -> None:
        self._source = source
        self._lock = threading.Lock()
        self._makeup_db = makeup_db
        self._env_in = 0.0
        self._env_out = 0.0
        self._latest: GrReading | None = None

    def start(self) -> None:
        self._source.start(on_samples=self._on_samples)

    def stop(self) -> None:
        self._source.stop()

    def set_makeup(self, makeup_db: float) -> None:
        with self._lock:
            self._makeup_db = makeup_db

    def _on_samples(
        self,
        in_block: npt.NDArray[np.float32],
        out_block: npt.NDArray[np.float32],
    ) -> None:
        rms_in = float(np.sqrt(np.mean(in_block.astype(np.float64) ** 2))) if in_block.size else 0.0
        rms_out = float(np.sqrt(np.mean(out_block.astype(np.float64) ** 2))) if out_block.size else 0.0

        a = self._ENV_COEFF
        self._env_in = (1.0 - a) * self._env_in + a * rms_in
        self._env_out = (1.0 - a) * self._env_out + a * rms_out

        in_db = _to_db(self._env_in)
        out_db = _to_db(self._env_out)
        with self._lock:
            makeup = self._makeup_db

        valid = in_db >= _SILENCE_DB
        gr_db = max(0.0, in_db + makeup - out_db) if valid else 0.0

        reading = GrReading(in_db=in_db, out_db=out_db, gr_db=gr_db, valid=valid, ts=time.monotonic())
        with self._lock:
            self._latest = reading

    def get_reading(self) -> GrReading | None:
        with self._lock:
            return self._latest
