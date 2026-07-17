"""Filter magnitude response calculators for parametric EQ curve rendering.

All math is vectorised numpy — we evaluate |H(e^jω)| analytically at each
graph frequency, no FFT, no scipy.

Three filter topologies are supported:
  - RBJ biquad (standard cookbook peaking, shelf, HP, LP)
  - Regalia-Mitra lattice (used by x42/fil4 and ZamEQ2 for peaking bands)
"""

from __future__ import annotations

import math

import numpy as np


FS = 48000.0
GRAPH_W = 320
FREQ_MIN_HZ = 20.0
FREQ_MAX_HZ = 20000.0

GRAPH_FREQS: np.ndarray = np.logspace(
    math.log10(FREQ_MIN_HZ), math.log10(FREQ_MAX_HZ), GRAPH_W
)


def _biquad_mag_db(
    b0: float, b1: float, b2: float, a1: float, a2: float
) -> np.ndarray:
    """Return |H(e^jω)| in dB at GRAPH_FREQS for a normalised biquad (a0 = 1)."""
    w = 2.0 * np.pi * GRAPH_FREQS / FS
    z1 = np.exp(-1j * w)
    z2 = z1 * z1
    num = b0 + b1 * z1 + b2 * z2
    den = 1.0 + a1 * z1 + a2 * z2
    return 20.0 * np.log10(np.abs(num / den) + 1e-12)


# ── RBJ biquad cookbook ───────────────────────────────────────────────────────


def rbj_peaking(f0: float, bw_oct: float, gain_db: float) -> np.ndarray:
    """RBJ peaking biquad magnitude at GRAPH_FREQS.

    ``bw_oct`` is bandwidth in octaves (the raw LV2 port value for all our
    custom EQ panels).
    """
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * f0 / FS
    cosw0 = math.cos(w0)
    sinw0 = math.sin(w0)
    alpha = sinw0 * math.sinh(
        math.log(2) / 2.0 * bw_oct * w0 / max(sinw0, 1e-12)
    )
    a0 = 1.0 + alpha / A
    b0 = (1.0 + alpha * A) / a0
    b1 = (-2.0 * cosw0) / a0
    b2 = (1.0 - alpha * A) / a0
    a1 = (-2.0 * cosw0) / a0
    a2 = (1.0 - alpha / A) / a0
    return _biquad_mag_db(b0, b1, b2, a1, a2)


def rbj_lowshelf(f0: float, q: float, gain_db: float) -> np.ndarray:
    """RBJ low-shelf biquad magnitude at GRAPH_FREQS."""
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * f0 / FS
    cosw0 = math.cos(w0)
    sinw0 = math.sin(w0)
    q_eff = 0.2129 + q / 2.25
    alpha = sinw0 / (2.0 * max(q_eff, 1e-4))
    two_sqrtA_alpha = 2.0 * math.sqrt(A) * alpha
    a0 = (A + 1.0) + (A - 1.0) * cosw0 + two_sqrtA_alpha
    b0 = (A * ((A + 1.0) - (A - 1.0) * cosw0 + two_sqrtA_alpha)) / a0
    b1 = (2.0 * A * ((A - 1.0) - (A + 1.0) * cosw0)) / a0
    b2 = (A * ((A + 1.0) - (A - 1.0) * cosw0 - two_sqrtA_alpha)) / a0
    a1 = (-2.0 * ((A - 1.0) + (A + 1.0) * cosw0)) / a0
    a2 = ((A + 1.0) + (A - 1.0) * cosw0 - two_sqrtA_alpha) / a0
    return _biquad_mag_db(b0, b1, b2, a1, a2)


def rbj_highshelf(f0: float, q: float, gain_db: float) -> np.ndarray:
    """RBJ high-shelf biquad magnitude at GRAPH_FREQS."""
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
    return _biquad_mag_db(b0, b1, b2, a1, a2)


def rbj_highpass(f0: float, q: float) -> np.ndarray:
    """RBJ highpass biquad magnitude at GRAPH_FREQS."""
    w0 = 2.0 * math.pi * f0 / FS
    cosw0 = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * max(q, 1e-4))
    a0 = 1.0 + alpha
    b0 = (1.0 + cosw0) / 2.0 / a0
    b1 = -(1.0 + cosw0) / a0
    b2 = (1.0 + cosw0) / 2.0 / a0
    a1 = (-2.0 * cosw0) / a0
    a2 = (1.0 - alpha) / a0
    return _biquad_mag_db(b0, b1, b2, a1, a2)


def rbj_lowpass(f0: float, q: float) -> np.ndarray:
    """RBJ lowpass biquad magnitude at GRAPH_FREQS."""
    w0 = 2.0 * math.pi * f0 / FS
    cosw0 = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * max(q, 1e-4))
    a0 = 1.0 + alpha
    b0 = (1.0 - cosw0) / 2.0 / a0
    b1 = (1.0 - cosw0) / a0
    b2 = (1.0 - cosw0) / 2.0 / a0
    a1 = (-2.0 * cosw0) / a0
    a2 = (1.0 - alpha) / a0
    return _biquad_mag_db(b0, b1, b2, a1, a2)


# ── Regalia-Mitra lattice (Fil4Paramsect) ─────────────────────────────────────


def regalia_mitra_peaking(f0: float, bw_oct: float, gain_db: float) -> np.ndarray:
    """Regalia-Mitra lattice peaking filter magnitude at GRAPH_FREQS.

    This is the topology used by x42/fil4 (Fil4Paramsect) and ZamEQ2
    (peq()).  ``bw_oct`` is bandwidth in octaves, passed directly into
    the lattice coefficient formula (matching the native x42 GUI).

    Coefficient derivation from x42 fil4's ``gui/fil4.c`` ``update_filter()``
    and ``get_filter_response()``.
    """
    freq_ratio = f0 / FS
    g = 10.0 ** (gain_db / 20.0)
    b = 7.0 * bw_oct * freq_ratio / math.sqrt(max(g, 1e-12))
    s2 = (1.0 - b) / (1.0 + b)
    s1 = -math.cos(2.0 * math.pi * freq_ratio)
    s1 *= 1.0 + s2
    gain_eff = 0.5 * (g - 1.0) * (1.0 - s2)

    w = 2.0 * np.pi * GRAPH_FREQS / FS
    c1 = np.cos(w)
    s1_w = np.sin(w)
    c2 = np.cos(2.0 * w)
    s2_w = np.sin(2.0 * w)

    x = c2 + s1 * c1 + s2
    y = s2_w + s1 * s1_w
    t1 = np.hypot(x, y)

    x += gain_eff * (c2 - 1.0)
    y += gain_eff * s2_w
    t2 = np.hypot(x, y)

    return 20.0 * np.log10(t2 / (t1 + 1e-12))
