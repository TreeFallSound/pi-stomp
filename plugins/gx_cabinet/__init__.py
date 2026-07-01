"""Registration for the Guitarix Cabinet Simulator plugin."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.gx_cabinet.panel import GxCabinetPanel

GX_CABINET_URI = "http://guitarix.sourceforge.net/plugins/gx_cabinet#CABINET"

register(
    GX_CABINET_URI,
    customization=PluginCustomization(
        panel_cls=GxCabinetPanel,
        display_name="GxCabinet",
    ),
)
