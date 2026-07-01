"""Advanced Compressor: full-screen panel with live GR meter."""

from __future__ import annotations

from plugins.advanced_compressor.panel import AdvancedCompressorPanel
from plugins.customization import PluginCustomization, register

ADVANCED_COMPRESSOR_URI = "http://moddevices.com/plugins/mod-devel/Advanced-Compressor"

register(
    ADVANCED_COMPRESSOR_URI,
    customization=PluginCustomization(
        panel_cls=AdvancedCompressorPanel,
        display_name="Advanced Compressor",
    ),
)
