"""Band specifications for the fil4 / x42-eq parametric EQ plugin."""

from __future__ import annotations

from plugins.eq.band_spec import BandSpec

BAND_SPECS: tuple[BandSpec, ...] = (
    BandSpec("HP", "hp", "HighPass", "HPfreq", "HPQ", None, None,
             20.0, 1250.0, 0.0, 1.4, color=(255, 110, 110)),
    BandSpec("LS", "shelf", "LSsec", "LSfreq", "LSq", "LSgain", "low",
             25.0, 400.0, 0.0625, 4.0, color=(255, 180, 80)),
    BandSpec("B1", "peak", "sec1", "freq1", "q1", "gain1", None,
             20.0, 2000.0, 0.0625, 4.0, color=(255, 230, 80)),
    BandSpec("B2", "peak", "sec2", "freq2", "q2", "gain2", None,
             40.0, 4000.0, 0.0625, 4.0, color=(130, 220, 110)),
    BandSpec("B3", "peak", "sec3", "freq3", "q3", "gain3", None,
             100.0, 10000.0, 0.0625, 4.0, color=(110, 200, 230)),
    BandSpec("B4", "peak", "sec4", "freq4", "q4", "gain4", None,
             200.0, 20000.0, 0.0625, 4.0, color=(140, 150, 240)),
    BandSpec("HS", "shelf", "HSsec", "HSfreq", "HSq", "HSgain", "high",
             1000.0, 16000.0, 0.0625, 4.0, color=(210, 130, 230)),
    BandSpec("LP", "lp", "LowPass", "LPfreq", "LPQ", None, None,
             500.0, 20000.0, 0.0, 1.4, color=(240, 140, 180)),
)

PLUGIN_ENABLE_SYM = "enable"
GLOBAL_GAIN_SYM = "gain"
