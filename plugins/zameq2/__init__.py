"""Registration for the ZamEQ2 plugin."""

from plugins.customization import PluginCustomization, register
from plugins.zameq2.panel import ZamEQ2Panel

register(
    "urn:zamaudio:ZamEQ2",
    customization=PluginCustomization(
        panel_cls=ZamEQ2Panel,
        display_name="ZamEQ2",
    ),
)
