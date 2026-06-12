"""Frequency-response magnitude (dB) for the fil4 / x42-eq filter chain.

V1 uses RBJ Audio EQ Cookbook biquads for peaks and shelves, and simple
analytical magnitude responses for HP/LP. This is an approximation of fil4's
exact topologies (paramsect for peaks, custom HP/LP with resonance remaps).
The peak/shelf curves are visually close enough for live tweaking; refine
later if MOD-UI overlay comparison shows meaningful drift.

All math is vectorised numpy. No scipy, no FFT — we evaluate
|H(e^jω)| = |B(z)/A(z)| at z = exp(-jω) analytically at each graph frequency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from plugins.eq.bands import BANDS, Band

# ── constants ────────────────────────────────────────────────────────────────

FS = 48000.0
GRAPH_W = 320
FREQ_MIN_HZ = 20.0
FREQ_MAX_HZ = 20000.0

# log-spaced graph frequencies, one per pixel column
GRAPH_FREQS: np.ndarray = np.logspace(np.log10(FREQ_MIN_HZ), np.log10(FREQ_MAX_HZ), GRAPH_W)


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
    bands: dict[str, BandParams]  # keyed by Band.name


# ── biquad evaluator ─────────────────────────────────────────────────────────


def _biquad_mag_db(b0: float, b1: float, b2: float, a1: float, a2: float) -> np.ndarray:
    """Return |H(e^jω)| in dB at GRAPH_FREQS for a normalised biquad (a0 = 1)."""
    w = 2.0 * np.pi * GRAPH_FREQS / FS
    z1 = np.exp(-1j * w)
    z2 = z1 * z1
    num = b0 + b1 * z1 + b2 * z2
    den = 1.0 + a1 * z1 + a2 * z2
    return 20.0 * np.log10(np.abs(num / den) + 1e-12)


# ── RBJ biquad coefficient helpers ───────────────────────────────────────────


def _rbj_peaking(f0: float, q: float, gain_db: float) -> tuple[float, float, float, float, float]:
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * f0 / FS
    cosw0 = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * max(q, 1e-4))
    a0 = 1.0 + alpha / A
    b0 = (1.0 + alpha * A) / a0
    b1 = (-2.0 * cosw0) / a0
    b2 = (1.0 - alpha * A) / a0
    a1 = (-2.0 * cosw0) / a0
    a2 = (1.0 - alpha / A) / a0
    return b0, b1, b2, a1, a2


def _rbj_lowshelf(f0: float, q: float, gain_db: float) -> tuple[float, float, float, float, float]:
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * f0 / FS
    cosw0 = math.cos(w0)
    sinw0 = math.sin(w0)
    # fil4 remaps port-Q to: q_eff = 0.2129 + port_Q / 2.25  (src/lv2.c)
    q_eff = 0.2129 + q / 2.25
    alpha = sinw0 / (2.0 * max(q_eff, 1e-4))
    two_sqrtA_alpha = 2.0 * math.sqrt(A) * alpha
    a0 = (A + 1.0) + (A - 1.0) * cosw0 + two_sqrtA_alpha
    b0 = (A * ((A + 1.0) - (A - 1.0) * cosw0 + two_sqrtA_alpha)) / a0
    b1 = (2.0 * A * ((A - 1.0) - (A + 1.0) * cosw0)) / a0
    b2 = (A * ((A + 1.0) - (A - 1.0) * cosw0 - two_sqrtA_alpha)) / a0
    a1 = (-2.0 * ((A - 1.0) + (A + 1.0) * cosw0)) / a0
    a2 = ((A + 1.0) + (A - 1.0) * cosw0 - two_sqrtA_alpha) / a0
    return b0, b1, b2, a1, a2


def _rbj_highshelf(f0: float, q: float, gain_db: float) -> tuple[float, float, float, float, float]:
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * f0 / FS
    cosw0 = math.cos(w0)
    sinw0 = math.sin(w0)
    q_eff = 0.2129 + q / 2.25
    alpha = sinw0 / (2.0 * max(q_eff, 1e-4))
    two_sqrtA_alpha = 2.0 * math.sqrt(A) * alpha
    a0 = (A + 1.0) - (A - 1.0) * cosw0 + two_sqrtA_alpha
    b0 = (A * ((A + 1.0) + (A - 1.0) * cosw0 + two_sqrtA_alpha)) / a0
    b1 = (-2.0 * A * ((A - 1.0) + (A + 1.0) * cosw0)) / a0
    b2 = (A * ((A + 1.0) + (A - 1.0) * cosw0 - two_sqrtA_alpha)) / a0
    a1 = (2.0 * ((A - 1.0) - (A + 1.0) * cosw0)) / a0
    a2 = ((A + 1.0) - (A - 1.0) * cosw0 - two_sqrtA_alpha) / a0
    return b0, b1, b2, a1, a2


def _rbj_highpass(f0: float, q: float) -> tuple[float, float, float, float, float]:
    """2nd-order high-pass — RBJ Q. fil4's HP is a different topology
    (1-pole cascade with feedback, ~12 dB/oct, RESHP(Q) remap); RBJ HP
    has the same slope and is visually close enough for v1."""
    w0 = 2.0 * math.pi * f0 / FS
    cosw0 = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * max(q, 1e-4))
    a0 = 1.0 + alpha
    b0 = (1.0 + cosw0) / 2.0 / a0
    b1 = -(1.0 + cosw0) / a0
    b2 = (1.0 + cosw0) / 2.0 / a0
    a1 = (-2.0 * cosw0) / a0
    a2 = (1.0 - alpha) / a0
    return b0, b1, b2, a1, a2


def _rbj_lowpass(f0: float, q: float) -> tuple[float, float, float, float, float]:
    """2nd-order low-pass. fil4's LP is a 4-pole cascade (~24 dB/oct,
    RESLP(Q) remap, pre-warped cutoff, plus a corrective high-shelf).
    For v1 we approximate with 2× cascaded RBJ LP at sqrt-Q to get ~24 dB/oct.
    """
    w0 = 2.0 * math.pi * f0 / FS
    cosw0 = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * max(q, 1e-4))
    a0 = 1.0 + alpha
    b0 = (1.0 - cosw0) / 2.0 / a0
    b1 = (1.0 - cosw0) / a0
    b2 = (1.0 - cosw0) / 2.0 / a0
    a1 = (-2.0 * cosw0) / a0
    a2 = (1.0 - alpha) / a0
    return b0, b1, b2, a1, a2


# ── per-stage magnitude (dB) ─────────────────────────────────────────────────


def _stage_db(band: Band, p: BandParams) -> np.ndarray:
    """Magnitude response in dB for one stage at GRAPH_FREQS."""
    f = max(min(p.freq, FS * 0.49), 1.0)
    if band.kind == "peak":
        return _biquad_mag_db(*_rbj_peaking(f, p.q, p.gain_db))
    if band.kind == "shelf":
        if band.name.startswith("L"):
            return _biquad_mag_db(*_rbj_lowshelf(f, p.q, p.gain_db))
        return _biquad_mag_db(*_rbj_highshelf(f, p.q, p.gain_db))
    if band.kind == "hp":
        # Two cascaded passes only if Q is high enough to matter; v1 uses single
        # 2nd-order RBJ HP. Slope is ~12 dB/oct (matches fil4's HP slope).
        return _biquad_mag_db(*_rbj_highpass(f, max(p.q, 0.5)))
    if band.kind == "lp":
        # 2× cascade for ~24 dB/oct (matches fil4's LP slope).
        single = _biquad_mag_db(*_rbj_lowpass(f, max(p.q, 0.5)))
        return single * 2.0
    raise ValueError(f"unknown band kind {band.kind!r}")


# ── public API ───────────────────────────────────────────────────────────────


class CurveCache:
    """Caches per-stage magnitude arrays keyed by params; only changed stages
    recompute. Aggregate curve is sum-in-dB across enabled stages plus the
    flat global gain offset, multiplied by a `shade` factor when the plugin
    is bypassed (renders dimmer to indicate inactive)."""

    def __init__(self) -> None:
        self._stage_cache: dict[tuple[str, tuple], np.ndarray] = {}

    def _stage_curve(self, band: Band, p: BandParams) -> np.ndarray:
        key = (band.name, p.key())
        cached = self._stage_cache.get(key)
        if cached is not None:
            return cached
        curve = _stage_db(band, p) if p.enabled else np.zeros(GRAPH_W)
        # bound cache size — drop old entries for this band
        for k in list(self._stage_cache.keys()):
            if k[0] == band.name:
                del self._stage_cache[k]
        self._stage_cache[key] = curve
        return curve

    def compute(self, state: EqState) -> np.ndarray:
        """Sum of all enabled stages, plus flat global gain, in dB."""
        total = np.full(GRAPH_W, state.global_gain_db, dtype=float)
        for band in BANDS:
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
