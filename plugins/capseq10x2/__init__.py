"""Registration for the mod-caps-Eq10X2 plugin."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.capseq10x2.menu_widget import CapsEq10X2MenuWidget

CAPS_EQ10X2_URI = "http://moddevices.com/plugins/caps/Eq10X2"

register(
    CAPS_EQ10X2_URI,
    customization=PluginCustomization(
        menu_widget_cls=CapsEq10X2MenuWidget,
        display_name="caps-Eq10X2",
    ),
)
