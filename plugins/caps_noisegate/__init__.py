"""Registration for the CAPS Noisegate plugin."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.caps_noisegate.menu_widget import CapsNoisegateMenuWidget

CAPS_NOISEGATE_URI = "http://moddevices.com/plugins/caps/Noisegate"

register(
    CAPS_NOISEGATE_URI,
    customization=PluginCustomization(
        menu_widget_cls=CapsNoisegateMenuWidget,
        display_name="CAPS Noisegate",
    ),
)