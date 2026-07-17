"""Band specifications for the rkr Parametric EQ (eqp) plugin."""

from __future__ import annotations

from plugins.eq.band_spec import BandSpec
from common.parameter import Symbol

BAND_SPECS: tuple[BandSpec, ...] = (
    BandSpec("Low", "peak", None, Symbol("LFREQ"), Symbol("LQ"), Symbol("LGAIN"), None,
             20.0, 1000.0, 0.033, 29.5, color=(255, 180, 80), gain_min=-30.0, gain_max=30.0),
    BandSpec("Mid", "peak", None, Symbol("MFREQ"), Symbol("MQ"), Symbol("MGAIN"), None,
             80.0, 8000.0, 0.033, 29.5, color=(130, 220, 110), gain_min=-30.0, gain_max=30.0),
    BandSpec("High", "peak", None, Symbol("HFREQ"), Symbol("HQ"), Symbol("HGAIN"), None,
             6000.0, 26000.0, 0.033, 29.5, color=(140, 150, 240), gain_min=-30.0, gain_max=30.0),
)
