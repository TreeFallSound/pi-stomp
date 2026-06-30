"""Registration for the TAP EQ/BW plugin."""

from plugins.customization import PluginCustomization, register
from plugins.tapeqbw.panel import TapEqBwPanel

register(
    "http://moddevices.com/plugins/tap/eqbw",
    customization=PluginCustomization(
        panel_cls=TapEqBwPanel,
        display_name="TAP EQ/BW",
    ),
)
