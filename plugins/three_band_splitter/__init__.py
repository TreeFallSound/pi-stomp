"""Registration for the DISTRHO 3 Band Splitter plugin."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.three_band_splitter.menu_widget import ThreeBandSplitterMenuWidget

THREE_BAND_SPLITTER_URI = "http://distrho.sf.net/plugins/3BandSplitter"

register(
    THREE_BAND_SPLITTER_URI,
    customization=PluginCustomization(
        menu_widget_cls=ThreeBandSplitterMenuWidget,
        display_name="3 Band Splitter",
    ),
)
