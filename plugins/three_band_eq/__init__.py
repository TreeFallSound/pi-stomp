"""Registration for the DISTRHO 3 Band EQ plugin."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.three_band_eq.window import ThreeBandEqWindow

THREE_BAND_EQ_URI = "http://distrho.sf.net/plugins/3BandEQ"

register(
    THREE_BAND_EQ_URI,
    customization=PluginCustomization(
        panel_cls=ThreeBandEqWindow,
        display_name="3 Band EQ",
    ),
)
