"""Registration for the DISTRHO 3 Band Splitter plugin."""

from __future__ import annotations

from common.parameter import Symbol
from modalapi.plugin_customization import PinnedParam
from plugins.customization import PluginCustomization, register
from uilib.misc import fmt_hz

THREE_BAND_SPLITTER_URI = "http://distrho.sf.net/plugins/3BandSplitter"

register(
    THREE_BAND_SPLITTER_URI,
    customization=PluginCustomization(
        display_name="3 Band Splitter",
        pinned_params=(
            PinnedParam(Symbol("low"), "Low"),
            PinnedParam(Symbol("mid"), "Mid"),
            PinnedParam(Symbol("high"), "High"),
            PinnedParam(Symbol("master"), "Master"),
            PinnedParam(Symbol("low_mid"), "L↔M", display_fn=fmt_hz),
            PinnedParam(Symbol("mid_high"), "M↔H", display_fn=fmt_hz),
        ),
    ),
)
