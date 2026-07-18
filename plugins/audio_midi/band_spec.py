"""Band specs for the IQaudIO Codec's 5-band DAC EQ (Dialog DA7213).

Frequencies are the DA7212/DA7213 datasheet's headline values at FS=48 kHz
(§13.22 "DAC 5-Band Equalizer", Table 32, p.49 of the Renesas DA7212
datasheet). The DA7213 shares the identical EQ block; verified against the
in-tree Linux ``da7213.h`` register map. Bands 1 and 5 are shelf filters
(LP/HP); 2-4 are band-pass. The frequency is the –1 dB cut-off for shelves
(at band gain = –3 dB) and the centre for band-pass.

Q/bandwidth is fixed in silicon and not exposed via ALSA (only gain is
controllable, –10.5..+12 dB in 1.5 dB steps), so ``GraphicBandSpec`` carries
no Q — the bar visualization is gain-only, matching the hardware.

Frequencies scale with the sample rate; 44.1 kHz variants (80/132/577/
2385/8784 Hz) are close enough that the 48 kHz labels read correctly on a
44.1 kHz device. If the device ever runs at 88.2/96 kHz the EQ is
unavailable (datasheet §13.22) and the menu is gated on
``audiocard.DAC_EQ is not None`` regardless.
"""

from __future__ import annotations

from plugins.eq.band_spec import GraphicBandSpec
from plugins.eq.graphic import _graphic_palette
from common.parameter import Symbol

# (name, freq_hz, alsa_eq_index). Names match the existing menu labels
# ("Low Band Gain" etc. in modhandler.system_menu_eq1_gain) so the readout
# reads consistently with the prior flat-menu surface.
_BANDS: list[tuple[str, float, int]] = [
    ("Low", 87.0, 1),
    ("L-Mid", 132.0, 2),
    ("Mid", 628.0, 3),
    ("H-Mid", 2596.0, 4),
    ("High", 9560.0, 5),
]

_colors = _graphic_palette(len(_BANDS))

BAND_SPECS: tuple[GraphicBandSpec, ...] = tuple(
    GraphicBandSpec(
        name=name,
        freq_hz=freq,
        gain_sym=Symbol(f"DAC EQ{idx}"),
        gain_min=-10.50,
        gain_max=12.0,
        color=color,
    )
    for (name, freq, idx), color in zip(_BANDS, _colors)
)