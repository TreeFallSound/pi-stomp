"""System Compressor: menu widget (mode/release/volume).

A full compressor panel (graph + GR meter) doesn't make sense here because
this plugin has no threshold, ratio, or knee ports — it's a streamlined
end-of-chain compressor with just mode/release/volume. A MultibandWindow
menu widget is the right fit.
"""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.system_compressor.widget import SystemCompressorWindow

SYSTEM_COMPRESSOR_URI = "http://moddevices.com/plugins/mod-devel/System-Compressor"

register(
    SYSTEM_COMPRESSOR_URI,
    customization=PluginCustomization(
        panel_cls=SystemCompressorWindow,
        display_name="System Compressor",
    ),
)
