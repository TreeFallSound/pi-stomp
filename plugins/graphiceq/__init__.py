"""Registration for the gx_graphiceq plugin."""

from plugins.customization import PluginCustomization, register
from plugins.graphiceq.panel import GxGraphicEqPanel

register(
    "http://guitarix.sourceforge.net/plugins/gx_graphiceq_#_graphiceq_",
    customization=PluginCustomization(
        panel_cls=GxGraphicEqPanel,
        display_name="gx_graphiceq",
    ),
)
