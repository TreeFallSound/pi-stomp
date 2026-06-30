"""Band specifications for the caps-Eq10 graphic EQ plugin (10 bands, octave)."""

from __future__ import annotations

from plugins.eq.band_spec import GraphicBandSpec
from plugins.eq.graphic import _graphic_palette

_BANDS: list[tuple[str, float, str]] = [
    ("31 Hz", 31.0, "band31hz"),
    ("63 Hz", 63.0, "band63hz"),
    ("125 Hz", 125.0, "band125hz"),
    ("250 Hz", 250.0, "band250hz"),
    ("500 Hz", 500.0, "band500hz"),
    ("1 kHz", 1000.0, "band1khz"),
    ("2 kHz", 2000.0, "band2khz"),
    ("4 kHz", 4000.0, "band4khz"),
    ("8 kHz", 8000.0, "band8khz"),
    ("16 kHz", 16000.0, "band16khz"),
]

_colors = _graphic_palette(len(_BANDS))

BAND_SPECS: tuple[GraphicBandSpec, ...] = tuple(
    GraphicBandSpec(name=name, freq_hz=freq, gain_sym=sym, gain_min=-48.0, gain_max=24.0, color=color)
    for (name, freq, sym), color in zip(_BANDS, _colors)
)
