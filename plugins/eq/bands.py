"""Band descriptor table for fil4 / x42-eq.

A "band" here is a Nav target on the EQ panel that maps to a group of LV2
control-port symbols on the fil4 plugin. The order in `BANDS` is the order
the Nav encoder cycles through them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


BandKind = Literal["hp", "lp", "shelf", "peak"]


@dataclass(frozen=True)
class Band:
    name: str  # short label shown in readout ("HP", "B1", ...)
    kind: BandKind
    enable_sym: str  # port symbol toggled by Nav shortpress
    freq_sym: str
    q_sym: str
    gain_sym: Optional[str]  # None for HP/LP (no gain axis)
    freq_min: float
    freq_max: float
    q_min: float
    q_max: float
    gain_min: float = -18.0
    gain_max: float = 18.0


# Order = Nav cycling order
BANDS: tuple[Band, ...] = (
    Band("HP", "hp", "HighPass", "HPfreq", "HPQ", None, 20.0, 1250.0, 0.0, 1.4),
    Band("LS", "shelf", "LSsec", "LSfreq", "LSq", "LSgain", 25.0, 400.0, 0.0625, 4.0),
    Band("B1", "peak", "sec1", "freq1", "q1", "gain1", 20.0, 2000.0, 0.0625, 4.0),
    Band("B2", "peak", "sec2", "freq2", "q2", "gain2", 40.0, 4000.0, 0.0625, 4.0),
    Band("B3", "peak", "sec3", "freq3", "q3", "gain3", 100.0, 10000.0, 0.0625, 4.0),
    Band("B4", "peak", "sec4", "freq4", "q4", "gain4", 200.0, 20000.0, 0.0625, 4.0),
    Band("HS", "shelf", "HSsec", "HSfreq", "HSq", "HSgain", 1000.0, 16000.0, 0.0625, 4.0),
    Band("LP", "lp", "LowPass", "LPfreq", "LPQ", None, 500.0, 20000.0, 0.0, 1.4),
)


# Per-band hue palette (RGB). Distinct, readable on black.
BAND_COLORS: dict[str, tuple[int, int, int]] = {
    "HP": (255, 110, 110),
    "LS": (255, 180, 80),
    "B1": (255, 230, 80),
    "B2": (130, 220, 110),
    "B3": (110, 200, 230),
    "B4": (140, 150, 240),
    "HS": (210, 130, 230),
    "LP": (240, 140, 180),
}


# Plugin-wide controls (not per-band)
PLUGIN_ENABLE_SYM = "enable"  # master bypass
GLOBAL_GAIN_SYM = "gain"  # flat dB offset (not exposed in v1)
