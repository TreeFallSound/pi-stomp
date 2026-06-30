"""Registration for the DISTRHO Audio EQ plugin."""

from plugins.customization import PluginCustomization, register
from plugins.distaq.panel import DistrhoAEqPanel

register(
    "urn:distrho:a-eq",
    customization=PluginCustomization(
        panel_cls=DistrhoAEqPanel,
        display_name="DISTRHO Audio EQ",
    ),
)
