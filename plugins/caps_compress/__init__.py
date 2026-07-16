"""CAPS Compress: full-screen panel with live GR meter."""

from __future__ import annotations

from plugins.caps_compress.panel import CapsCompressPanel
from plugins.customization import PluginCustomization, register

CAPS_COMPRESS_URI = "http://moddevices.com/plugins/caps/Compress"
CAPS_COMPRESSX2_URI = "http://moddevices.com/plugins/caps/CompressX2"

register(
    CAPS_COMPRESS_URI,
    CAPS_COMPRESSX2_URI,
    customization=PluginCustomization(
        panel_cls=CapsCompressPanel,
        display_name="CAPS Compress",
    ),
)
