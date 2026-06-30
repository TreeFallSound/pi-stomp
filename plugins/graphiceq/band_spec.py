"""Band specifications for the gx_graphiceq plugin (11 bands, ISO)."""

from __future__ import annotations

from plugins.eq.band_spec import GraphicBandSpec
from plugins.eq.graphic import _graphic_palette

# LV2 uppercases the symbols to G1..G11. The plugin's TTL declares the ports
# in a non-sequential order (G10, G11, G1, ...), but that order is only the
# LV2 wrapper layout — the actual band↔symbol mapping is sequential.
_BANDS: list[tuple[str, float, str]] = [
    ("31 Hz", 31.0, "G1"),
    ("63 Hz", 63.0, "G2"),
    ("125 Hz", 125.0, "G3"),
    ("250 Hz", 250.0, "G4"),
    ("500 Hz", 500.0, "G5"),
    ("1 kHz", 1000.0, "G6"),
    ("2 kHz", 2000.0, "G7"),
    ("4 kHz", 4000.0, "G8"),
    ("8 kHz", 8000.0, "G9"),
    ("16 kHz", 16000.0, "G10"),
    ("20 kHz", 20000.0, "G11"),
]

_colors = _graphic_palette(len(_BANDS))

BAND_SPECS: tuple[GraphicBandSpec, ...] = tuple(
    GraphicBandSpec(name=name, freq_hz=freq, gain_sym=sym, gain_min=-30.0, gain_max=20.0, color=color)
    for (name, freq, sym), color in zip(_BANDS, _colors)
)
