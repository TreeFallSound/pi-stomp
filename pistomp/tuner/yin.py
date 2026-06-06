from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


# Sub-sample interpolation basin width: CMND samples within this band above the trough
# minimum are averaged (centroid) to locate the period. See detect_pitch Step 4.
_TROUGH_BAND = 0.05


@dataclass(frozen=True)
class PitchEstimate:
    freq: float
    yin_error: float  # CMND value at tau_est; 0 = perfect, approaching 1 = unreliable


def detect_pitch(
    frame: npt.NDArray[np.float32],
    sample_rate: int,
    threshold: float = 0.10,
    freq_min: float = 30.0,
    freq_max: float = 1300.0,
    window: int | None = None,
) -> PitchEstimate | None:
    """YIN pitch detection. Returns PitchEstimate or None if no confident pitch found.

    Implements: de Cheveigné & Kawahara (2002), J. Acoust. Soc. Am. 111(4).

    window: explicit YIN correlation window W; defaults to len(frame)//2.
            frame must be at least W + sample_rate/freq_min samples long.
    """
    N = len(frame)
    half = window if window is not None else N // 2

    tau_min = max(2, int(sample_rate / freq_max))
    tau_max = min(half - 1, int(sample_rate / freq_min) + 1)

    if tau_min >= tau_max:
        return None

    # Step 1: difference function via FFT.
    # d(τ) = Σⱼ(x[j] - x[j+τ])² = E₀ + trailing(τ) - 2·xcorr(τ)
    # where E₀ = Σx[0:W]², trailing(τ) = Σx[τ:τ+W]², xcorr(τ) = Σx[j]·x[j+τ] for j∈[0,W)
    x = frame.astype(np.float64)
    W = half

    x_sq_cs = np.empty(N + 1, dtype=np.float64)
    x_sq_cs[0] = 0.0
    np.cumsum(x * x, out=x_sq_cs[1:])
    E0 = x_sq_cs[W]
    tau_range = np.arange(tau_max + 1)
    trailing = x_sq_cs[tau_range + W] - x_sq_cs[tau_range]

    # xcorr via FFT; n_fft must be >= W + N to avoid circular aliasing
    n_fft = 1 << (W + N - 1).bit_length()
    a = np.zeros(n_fft, dtype=np.float64)
    a[:W] = x[:W]
    # irfft(rfft(x)*conj(rfft(a)))[τ] = Σⱼ x[j+τ]·a[j] — positive-lag correlation
    xcorr = np.fft.irfft(np.fft.rfft(x, n=n_fft) * np.fft.rfft(a).conj())[:tau_max + 1]

    diff = E0 + trailing - 2.0 * xcorr
    diff[0] = 0.0

    # Step 2: cumulative mean normalised difference (CMND), eq. 8 in the paper.
    cumsum = np.cumsum(diff[1:tau_max + 1])
    taus = np.arange(1, tau_max + 1, dtype=np.float64)
    cmnd = np.ones(tau_max + 1, dtype=np.float64)
    cmnd[1:tau_max + 1] = 1.0
    np.divide(diff[1:tau_max + 1] * taus, cumsum, out=cmnd[1:tau_max + 1], where=cumsum > 0.0)

    # Step 3: absolute threshold — first dip below threshold, walk to its bottom.
    # No argmin fallback: a reading that doesn't pass the threshold is not published.
    tau_est = -1
    tau = tau_min
    while tau < tau_max:
        if cmnd[tau] < threshold:
            while tau + 1 <= tau_max and cmnd[tau + 1] <= cmnd[tau]:
                tau += 1
            tau_est = tau
            break
        tau += 1

    if tau_est < 1:
        return None

    # Step 4: sub-sample period = cmnd-weighted centroid of the trough basin. The
    # textbook 3-point parabola is degenerate on a flat trough bottom (two ~equal
    # adjacent samples, true minimum between them): it snaps ±1 sample rather than
    # landing between, a bistable ~12-cent waver at guitar-string frequencies. The
    # centroid averages the basin; a sharp single-sample trough falls back to parabola.
    cmin = cmnd[tau_est]
    band = cmin + _TROUGH_BAND
    lo = hi = tau_est
    while lo - 1 >= tau_min and cmnd[lo - 1] <= band:
        lo -= 1
    while hi + 1 <= tau_max and cmnd[hi + 1] <= band:
        hi += 1

    if hi > lo:
        basin = np.arange(lo, hi + 1, dtype=np.float64)
        weights = band - cmnd[lo:hi + 1]  # >= 0 by construction; peaks at the minimum
        tau_refined = float(np.sum(basin * weights) / np.sum(weights))
    elif tau_min < tau_est < tau_max:
        # Single-sample basin (ultra-sharp trough): fall back to the 3-point parabola.
        s0, s1, s2 = cmnd[tau_est - 1], cmnd[tau_est], cmnd[tau_est + 1]
        denom = 2.0 * (2.0 * s1 - s0 - s2)
        correction = (s0 - s2) / denom if abs(denom) > 1e-10 else 0.0
        tau_refined = tau_est + (correction if abs(correction) < 1.0 else 0.0)
    else:
        tau_refined = float(tau_est)

    if tau_refined <= 0.0:
        return None

    return PitchEstimate(freq=sample_rate / tau_refined, yin_error=cmin)
