"""Frequency-response magnitude (dB) for parametric EQ filter chains.

Delegates actual filter magnitude computation to ``filters.py``; this module
owns the ``CurveCache`` and coordinate-mapping helpers.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from plugins.eq.band_spec import BandSpec
from plugins.eq.filters import (
    FS,
    FREQ_MIN_HZ,
    FREQ_MAX_HZ,
    GRAPH_W,
    rbj_highpass,
    rbj_lowpass,
    rbj_lowshelf,
    rbj_highshelf,
    rbj_peaking,
    regalia_mitra_peaking,
)

# ── per-band parameter snapshot ──────────────────────────────────────────────


@dataclass(frozen=True)
class BandParams:
    enabled: bool
    freq: float
    q: float
    gain_db: float = 0.0  # ignored for HP/LP

    def key(self) -> tuple:
        return (self.enabled, round(self.freq, 4), round(self.q, 6), round(self.gain_db, 4))


@dataclass(frozen=True)
class EqState:
    """Snapshot of all params needed to render the curve."""

    plugin_enabled: bool
    global_gain_db: float
    bands: dict[str, BandParams]  # keyed by BandSpec.name


# ── per-stage magnitude (dB) ─────────────────────────────────────────────────


def _stage_db(band: BandSpec, p: BandParams) -> np.ndarray:
    """Magnitude response in dB for one stage at GRAPH_FREQS."""
    f = max(min(p.freq, FS * 0.49), 1.0)
    if band.kind == "peak":
        if band.filter_topology == "regalia_mitra":
            return regalia_mitra_peaking(f, p.q, p.gain_db)
        return rbj_peaking(f, p.q, p.gain_db)
    if band.kind == "shelf":
        if band.shelf_side == "low":
            return rbj_lowshelf(f, p.q, p.gain_db)
        return rbj_highshelf(f, p.q, p.gain_db)
    if band.kind == "hp":
        return rbj_highpass(f, max(p.q, 0.5))
    if band.kind == "lp":
        return rbj_lowpass(f, max(p.q, 0.5)) * 2.0
    raise ValueError(f"unknown band kind {band.kind!r}")


# ── public API ───────────────────────────────────────────────────────────────


class CurveCache:
    """Caches per-stage magnitude arrays keyed by params; only changed stages
    recompute. Aggregate curve is sum-in-dB across enabled stages plus the
    flat global gain offset."""

    def __init__(self) -> None:
        self._stage_cache: dict[tuple[str, tuple], np.ndarray] = {}

    def _stage_curve(self, band: BandSpec, p: BandParams) -> np.ndarray:
        key = (band.name, p.key())
        cached = self._stage_cache.get(key)
        if cached is not None:
            return cached
        curve = _stage_db(band, p) if p.enabled else np.zeros(GRAPH_W)
        for k in list(self._stage_cache.keys()):
            if k[0] == band.name:
                del self._stage_cache[k]
        self._stage_cache[key] = curve
        return curve

    def compute(self, bands: Sequence[BandSpec], state: EqState) -> np.ndarray:
        """Sum of all enabled stages, plus flat global gain, in dB."""
        total = np.full(GRAPH_W, state.global_gain_db, dtype=float)
        for band in bands:
            p = state.bands.get(band.name)
            if p is None:
                continue
            total = total + self._stage_curve(band, p)
        return total


def db_to_y(curve_db: np.ndarray, y_top: int, y_bot: int, db_max: float = 18.0) -> np.ndarray:
    """Map dB values to pixel rows in [y_top, y_bot]. y_top corresponds to
    +db_max, y_bot to -db_max. Values are clipped."""
    return db_to_y_float(curve_db, y_top, y_bot, db_max).round().astype(int)


def db_to_y_float(curve_db: np.ndarray, y_top: int, y_bot: int, db_max: float = 18.0) -> np.ndarray:
    """Same mapping as `db_to_y` but returns float pixel positions — used by
    the AA curve rasterizer, which needs sub-pixel y to anti-alias the line."""
    span = y_bot - y_top
    norm = (db_max - np.clip(curve_db, -db_max, db_max)) / (2.0 * db_max)
    return y_top + norm * span


def freq_to_x(freq_hz: float | np.ndarray) -> int | np.ndarray:
    """Map a frequency (or array) to a pixel column in [0, GRAPH_W-1]."""
    norm = (np.log10(np.asarray(freq_hz)) - math.log10(FREQ_MIN_HZ)) / (
        math.log10(FREQ_MAX_HZ) - math.log10(FREQ_MIN_HZ)
    )
    x = (norm * (GRAPH_W - 1)).round().astype(int)
    if np.isscalar(freq_hz):
        return int(x)
    return x
