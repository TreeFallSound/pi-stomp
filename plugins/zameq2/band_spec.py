"""Band specifications for the ZamEQ2 parametric EQ plugin."""

from __future__ import annotations

from plugins.eq.band_spec import BandSpec
from common.parameter import Symbol

BAND_SPECS: tuple[BandSpec, ...] = (
    BandSpec("L", "shelf", None, Symbol("fl"), None, Symbol("boostl"), "low",
             20.0, 14000.0, 0.1, 6.0, color=(255, 180, 80), gain_min=-50.0, gain_max=20.0),
    BandSpec("1", "peak", None, Symbol("f1"), Symbol("bw1"), Symbol("boost1"), None,
             20.0, 14000.0, 0.1, 6.0, color=(255, 230, 80), gain_min=-50.0, gain_max=20.0),
    BandSpec("2", "peak", None, Symbol("f2"), Symbol("bw2"), Symbol("boost2"), None,
             20.0, 14000.0, 0.1, 6.0, color=(130, 220, 110), gain_min=-50.0, gain_max=20.0),
    BandSpec("H", "shelf", None, Symbol("fh"), None, Symbol("boosth"), "high",
             20.0, 14000.0, 0.1, 6.0, color=(210, 130, 230), gain_min=-50.0, gain_max=20.0),
)
