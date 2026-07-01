"""Registration for the CAPS Noisegate plugin."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.caps_noisegate.window import CapsNoisegateWindow

CAPS_NOISEGATE_URI = "http://moddevices.com/plugins/caps/Noisegate"

register(
    CAPS_NOISEGATE_URI,
    customization=PluginCustomization(
        panel_cls=CapsNoisegateWindow,
        display_name="CAPS Noisegate",
    ),
)