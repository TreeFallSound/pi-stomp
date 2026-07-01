"""Registration for the mod-caps-Eq10X2 plugin."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.capseq10x2.window import CapsEq10X2Window

CAPS_EQ10X2_URI = "http://moddevices.com/plugins/caps/Eq10X2"

register(
    CAPS_EQ10X2_URI,
    customization=PluginCustomization(
        panel_cls=CapsEq10X2Window,
        display_name="caps-Eq10X2",
    ),
)
