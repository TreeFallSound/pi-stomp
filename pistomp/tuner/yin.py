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


class YinDetector:
    """YIN pitch detector with pre-allocated scratch arrays.

    Implements: de Cheveigné & Kawahara (2002), J. Acoust. Soc. Am. 111(4).
    """

    def __init__(
        self,
        frame_size: int,
        sample_rate: int,
        threshold: float = 0.10,
        freq_min: float = 30.0,
        freq_max: float = 1300.0,
        window: int | None = None,
    ) -> None:
        self._sample_rate = sample_rate
        self._threshold = threshold

        N = frame_size
        W = window if window is not None else N // 2
        self._W = W
        self._N = N
        self._tau_min = max(2, int(sample_rate / freq_max))
        self._tau_max = min(W - 1, int(sample_rate / freq_min) + 1)
        self._n_fft = 1 << (W + N - 1).bit_length()

        # Pre-allocated scratch
        self._x_sq_cs = np.empty(N + 1, dtype=np.float32)
        self._a = np.zeros(self._n_fft, dtype=np.float32)  # [W:] stays zero
        self._tau_range = np.arange(self._tau_max + 1)  # constant
        self._taus = np.arange(1, self._tau_max + 1, dtype=np.float32)  # constant
        self._cmnd = np.ones(self._tau_max + 1, dtype=np.float32)

    def detect(self, frame: npt.NDArray[np.float32]) -> PitchEstimate | None:
        tau_min = self._tau_min
        tau_max = self._tau_max
        if tau_min >= tau_max:
            return None

        x = frame
        W = self._W
        x_sq_cs = self._x_sq_cs
        a = self._a
        tau_range = self._tau_range
        taus = self._taus
        cmnd = self._cmnd

        # Step 1: difference function via FFT.
        # d(τ) = Σⱼ(x[j] - x[j+τ])² = E₀ + trailing(τ) - 2·xcorr(τ)
        x_sq_cs[0] = 0.0
        np.cumsum(x * x, out=x_sq_cs[1:])
        E0 = x_sq_cs[W]
        trailing = x_sq_cs[tau_range + W] - x_sq_cs[tau_range]

        # xcorr via FFT; n_fft must be >= W + N to avoid circular aliasing
        a[:W] = x[:W]
        # irfft(rfft(x)*conj(rfft(a)))[τ] = Σⱼ x[j+τ]·a[j] — positive-lag correlation
        xcorr = np.fft.irfft(np.fft.rfft(x, n=self._n_fft) * np.fft.rfft(a).conj())[: tau_max + 1]

        diff = E0 + trailing - 2 * xcorr
        diff[0] = 0.0

        # Step 2: cumulative mean normalised difference (CMND), eq. 8 in the paper.
        cumsum = np.cumsum(diff[1 : tau_max + 1])
        cmnd[0] = 1.0
        # where=False positions keep their previous value; cumsum==0 only on silence,
        # which the engine's RMS gate filters before calling detect().
        np.divide(diff[1 : tau_max + 1] * taus, cumsum, out=cmnd[1 : tau_max + 1], where=cumsum > 0.0)

        # Step 3: absolute threshold — first dip below threshold, walk to its bottom.
        # No argmin fallback: a reading that doesn't pass the threshold is not published.
        hits = np.nonzero(cmnd[tau_min:tau_max] < self._threshold)[0]
        if hits.size == 0:
            return None
        tau = tau_min + int(hits[0])
        while tau + 1 <= tau_max and cmnd[tau + 1] <= cmnd[tau]:
            tau += 1
        tau_est = tau

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
            weights = band - cmnd[lo : hi + 1]
            tau_refined = float(np.sum(basin * weights) / np.sum(weights))
        elif tau_min < tau_est < tau_max:
            s0, s1, s2 = cmnd[tau_est - 1], cmnd[tau_est], cmnd[tau_est + 1]
            denom = 2.0 * (2.0 * s1 - s0 - s2)
            correction = (s0 - s2) / denom if abs(denom) > 1e-10 else 0.0
            tau_refined = tau_est + (correction if abs(correction) < 1.0 else 0.0)
        else:
            tau_refined = float(tau_est)

        if tau_refined <= 0.0:
            return None

        return PitchEstimate(freq=self._sample_rate / tau_refined, yin_error=float(cmin))


def detect_pitch(
    frame: npt.NDArray[np.float32],
    sample_rate: int,
    threshold: float = 0.10,
    freq_min: float = 30.0,
    freq_max: float = 1300.0,
    window: int | None = None,
) -> PitchEstimate | None:
    """Convenience wrapper — creates a fresh YinDetector per call. Use YinDetector
    directly when calling repeatedly on frames of a fixed size."""
    return YinDetector(
        len(frame),
        sample_rate,
        threshold=threshold,
        freq_min=freq_min,
        freq_max=freq_max,
        window=window,
    ).detect(frame)
