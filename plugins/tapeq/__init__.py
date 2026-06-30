"""Registration for the TAP EQ plugin."""

from plugins.customization import PluginCustomization, register
from plugins.tapeq.panel import TapEqPanel

register(
    "http://moddevices.com/plugins/tap/eq",
    customization=PluginCustomization(
        panel_cls=TapEqPanel,
        display_name="TAP EQ",
    ),
)
