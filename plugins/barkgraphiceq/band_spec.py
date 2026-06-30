"""Band specifications for the gx_barkgraphiceq plugin (24 bands, Bark scale)."""

from __future__ import annotations

from plugins.eq.band_spec import GraphicBandSpec
from plugins.eq.graphic import _graphic_palette

# Bark-scale center frequencies (approximate, from Bark scale literature).
# The TTL manifest declares only gain ports G1-G24 with no frequency metadata.
_BARK_FREQS: list[float] = [
    50, 150, 250, 350, 450, 570, 700, 840,
    1000, 1170, 1370, 1600, 1850, 2150, 2500, 2900,
    3400, 4000, 4800, 5800, 7000, 8500, 10500, 13500,
]

_colors = _graphic_palette(len(_BARK_FREQS))

BAND_SPECS: tuple[GraphicBandSpec, ...] = tuple(
    GraphicBandSpec(
        name=f"G{i+1}",
        freq_hz=freq,
        gain_sym=f"G{i+1}",
        gain_min=-30.0,
        gain_max=20.0,
        color=color,
    )
    for i, (freq, color) in enumerate(zip(_BARK_FREQS, _colors))
)
