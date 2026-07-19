"""Band specs for the IQaudIO Codec's 5-band DAC EQ (Dialog DA7213).

Centre/cut-off frequencies come from Table 32 ("DAC 5-band equaliser
turnover/centre frequencies", §13.22, p.46 of the Renesas DA7212 datasheet
rev 3.5). The DA7213 shares the identical EQ block; verified against the
in-tree Linux ``da7213.h`` register map. Bands 1 and 5 are shelf filters
(LP/HP); 2-4 are band-pass. The frequency is the -1 dB cut-off for shelves
(at band gain = -3 dB) and the centre for band-pass.

Every frequency scales with the sample rate, so the table is keyed by it —
``band_specs_for`` returns ``None`` at 88.2/96 kHz, where the datasheet marks
the whole EQ N/A. Only the frequencies vary; names, symbols and gain range
are rate-invariant.

Q/bandwidth is fixed in silicon and not exposed via ALSA (only gain is
controllable, -10.5..+12 dB in 1.5 dB steps), so ``GraphicBandSpec`` carries
no Q — the bar visualization is gain-only, matching the hardware.
"""

from __future__ import annotations

from plugins.eq.band_spec import GraphicBandSpec
from plugins.eq.graphic import _graphic_palette
from common.parameter import Symbol

# Names match the existing menu labels ("Low Band Gain" etc. in
# modhandler.system_menu_eq1_gain) so the readout reads consistently with the
# prior flat-menu surface. Order is the ALSA mixer order (DAC EQ1..5).
_BAND_NAMES: list[str] = ["Low", "L-Mid", "Mid", "H-Mid", "High"]

# Datasheet Table 32. 88.2/96 kHz are listed N/A and so are absent.
_FREQS_BY_RATE: dict[int, tuple[float, float, float, float, float]] = {
    8000: (21, 85, 563, 1151, 2909),
    11025: (29, 117, 776, 2137, 4009),
    12000: (31, 128, 845, 2326, 4364),
    16000: (41, 90, 441, 2128, 5840),
    22050: (56, 124, 607, 2933, 8048),
    24000: (61, 135, 664, 3192, 8759),
    32000: (58, 95, 418, 1731, 6374),
    44100: (80, 132, 577, 2385, 8784),
    48000: (87, 143, 628, 2596, 9560),
}

_REFERENCE_RATE = 48000

_colors = _graphic_palette(len(_BAND_NAMES))


def _specs(freqs: tuple[float, float, float, float, float]) -> tuple[GraphicBandSpec, ...]:
    return tuple(
        GraphicBandSpec(
            name=name,
            freq_hz=freq,
            gain_sym=Symbol(f"DAC EQ{idx}"),
            gain_min=-10.50,
            gain_max=12.0,
            color=color,
        )
        for idx, (name, freq, color) in enumerate(zip(_BAND_NAMES, freqs, _colors), 1)
    )


def band_specs_for(sample_rate: int) -> tuple[GraphicBandSpec, ...] | None:
    """Specs for ``sample_rate``, or None at a rate the EQ can't run at."""
    freqs = _FREQS_BY_RATE.get(sample_rate)
    return None if freqs is None else _specs(freqs)


# Rate-invariant reference: names, symbols and gain range for the write path
# and for laying out the (greyed) bars when the rate is unsupported.
BAND_SPECS: tuple[GraphicBandSpec, ...] = _specs(_FREQS_BY_RATE[_REFERENCE_RATE])
