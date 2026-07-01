"""Calf Mono Compressor: full-screen panel with live GR meter."""

from __future__ import annotations

from plugins.calf_monocompressor.panel import CalfMonoCompressorPanel
from plugins.customization import PluginCustomization, register

CALF_MONOCOMPRESSOR_URI = "http://calf.sourceforge.net/plugins/MonoCompressor"

register(
    CALF_MONOCOMPRESSOR_URI,
    customization=PluginCustomization(
        panel_cls=CalfMonoCompressorPanel,
        display_name="Calf Mono Compressor",
    ),
)
