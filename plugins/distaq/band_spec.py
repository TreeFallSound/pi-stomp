"""Band specifications for the DISTRHO Audio EQ (a-eq) parametric EQ plugin."""

from __future__ import annotations

from plugins.eq.band_spec import BandSpec
from common.parameter import Symbol

BAND_SPECS: tuple[BandSpec, ...] = (
    BandSpec("L", "shelf", Symbol("filtogl"), Symbol("freql"), None, Symbol("gl"), "low",
             20.0, 20000.0, 0.1, 4.0, color=(255, 180, 80), gain_min=-20.0, gain_max=20.0),
    BandSpec("1", "peak", Symbol("filtog1"), Symbol("freq1"), Symbol("bw1"), Symbol("g1"), None,
             20.0, 20000.0, 0.1, 4.0, color=(255, 230, 80), gain_min=-20.0, gain_max=20.0, q_is_bw_oct=True),
    BandSpec("2", "peak", Symbol("filtog2"), Symbol("freq2"), Symbol("bw2"), Symbol("g2"), None,
             20.0, 20000.0, 0.1, 4.0, color=(130, 220, 110), gain_min=-20.0, gain_max=20.0, q_is_bw_oct=True),
    BandSpec("3", "peak", Symbol("filtog3"), Symbol("freq3"), Symbol("bw3"), Symbol("g3"), None,
             20.0, 20000.0, 0.1, 4.0, color=(110, 200, 230), gain_min=-20.0, gain_max=20.0, q_is_bw_oct=True),
    BandSpec("4", "peak", Symbol("filtog4"), Symbol("freq4"), Symbol("bw4"), Symbol("g4"), None,
             20.0, 20000.0, 0.1, 4.0, color=(140, 150, 240), gain_min=-20.0, gain_max=20.0, q_is_bw_oct=True),
    BandSpec("H", "shelf", Symbol("filtogh"), Symbol("freqh"), None, Symbol("gh"), "high",
             20.0, 20000.0, 0.1, 4.0, color=(210, 130, 230), gain_min=-20.0, gain_max=20.0),
)
