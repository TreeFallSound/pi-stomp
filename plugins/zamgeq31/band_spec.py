"""Band specifications for the ZamGEQ31 graphic EQ plugin (29 bands, 1/3-octave ISO)."""

from __future__ import annotations

from plugins.eq.band_spec import GraphicBandSpec
from plugins.eq.graphic import _graphic_palette

# 1/3-octave ISO center frequencies from 32 Hz to 20 kHz.
_BANDS: list[tuple[str, float, str]] = [
    ("32Hz", 32.0, "band1"),
    ("40Hz", 40.0, "band2"),
    ("50Hz", 50.0, "band3"),
    ("63Hz", 63.0, "band4"),
    ("79Hz", 79.0, "band5"),
    ("100Hz", 100.0, "band6"),
    ("126Hz", 126.0, "band7"),
    ("158Hz", 158.0, "band8"),
    ("200Hz", 200.0, "band9"),
    ("251Hz", 251.0, "band10"),
    ("316Hz", 316.0, "band11"),
    ("398Hz", 398.0, "band12"),
    ("501Hz", 501.0, "band13"),
    ("631Hz", 631.0, "band14"),
    ("794Hz", 794.0, "band15"),
    ("999Hz", 999.0, "band16"),
    ("1257Hz", 1257.0, "band17"),
    ("1584Hz", 1584.0, "band18"),
    ("1997Hz", 1997.0, "band19"),
    ("2514Hz", 2514.0, "band20"),
    ("3165Hz", 3165.0, "band21"),
    ("3986Hz", 3986.0, "band22"),
    ("5017Hz", 5017.0, "band23"),
    ("6318Hz", 6318.0, "band24"),
    ("7963Hz", 7963.0, "band25"),
    ("10032Hz", 10032.0, "band26"),
    ("12662Hz", 12662.0, "band27"),
    ("16081Hz", 16081.0, "band28"),
    ("20801Hz", 20801.0, "band29"),
]

_colors = _graphic_palette(len(_BANDS))

BAND_SPECS: tuple[GraphicBandSpec, ...] = tuple(
    GraphicBandSpec(name=name, freq_hz=freq, gain_sym=sym, gain_min=-12.0, gain_max=12.0, color=color)
    for (name, freq, sym), color in zip(_BANDS, _colors)
)
