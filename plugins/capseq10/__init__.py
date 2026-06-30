"""Registration for the caps-Eq10 plugin."""

from plugins.customization import PluginCustomization, register
from plugins.capseq10.panel import CapsEq10Panel

CAPSEQ10_URI = "http://moddevices.com/plugins/caps/Eq10"

register(
    CAPSEQ10_URI,
    customization=PluginCustomization(
        panel_cls=CapsEq10Panel,
        display_name="caps-Eq10",
    ),
)
