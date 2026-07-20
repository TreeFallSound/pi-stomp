from plugins.customization import PluginCustomization, register
from plugins.calf_eq5.panel import CalfEq5Panel

register(
    "http://calf.sourceforge.net/plugins/Equalizer5Band",
    customization=PluginCustomization(
        panel_cls=CalfEq5Panel,
        display_name="Calf EQ5",
    ),
)
