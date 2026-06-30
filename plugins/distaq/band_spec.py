"""Band specifications for the DISTRHO Audio EQ (a-eq) parametric EQ plugin."""

from __future__ import annotations

from plugins.eq.band_spec import BandSpec

BAND_SPECS: tuple[BandSpec, ...] = (
    BandSpec("L", "shelf", "filtogl", "freql", None, "gl", "low",
             20.0, 20000.0, 0.1, 4.0, color=(255, 180, 80), gain_min=-20.0, gain_max=20.0),
    BandSpec("1", "peak", "filtog1", "freq1", "bw1", "g1", None,
             20.0, 20000.0, 0.1, 4.0, color=(255, 230, 80), gain_min=-20.0, gain_max=20.0),
    BandSpec("2", "peak", "filtog2", "freq2", "bw2", "g2", None,
             20.0, 20000.0, 0.1, 4.0, color=(130, 220, 110), gain_min=-20.0, gain_max=20.0),
    BandSpec("3", "peak", "filtog3", "freq3", "bw3", "g3", None,
             20.0, 20000.0, 0.1, 4.0, color=(110, 200, 230), gain_min=-20.0, gain_max=20.0),
    BandSpec("4", "peak", "filtog4", "freq4", "bw4", "g4", None,
             20.0, 20000.0, 0.1, 4.0, color=(140, 150, 240), gain_min=-20.0, gain_max=20.0),
    BandSpec("H", "shelf", "filtogh", "freqh", None, "gh", "high",
             20.0, 20000.0, 0.1, 4.0, color=(210, 130, 230), gain_min=-20.0, gain_max=20.0),
)
