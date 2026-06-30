"""Registration for the ZamGEQ31 plugin."""

from plugins.customization import PluginCustomization, register
from plugins.zamgeq31.panel import ZamGEQ31Panel

register(
    "urn:zamaudio:ZamGEQ31",
    customization=PluginCustomization(
        panel_cls=ZamGEQ31Panel,
        display_name="ZamGEQ31",
    ),
)
