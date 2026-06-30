"""Registration for the gx_barkgraphiceq plugin."""

from plugins.customization import PluginCustomization, register
from plugins.barkgraphiceq.panel import GxBarkGraphicEqPanel

register(
    "http://guitarix.sourceforge.net/plugins/gx_barkgraphiceq_#_barkgraphiceq_",
    customization=PluginCustomization(
        panel_cls=GxBarkGraphicEqPanel,
        display_name="gx_barkgraphiceq",
    ),
)
