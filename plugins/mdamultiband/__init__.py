"""Registration for the mod-mda-MultiBand plugin."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.mdamultiband.window import MdaMultiBandWindow

MDA_MULTIBAND_URI = "http://moddevices.com/plugins/mda/MultiBand"

register(
    MDA_MULTIBAND_URI,
    customization=PluginCustomization(
        panel_cls=MdaMultiBandWindow,
        display_name="MDA MultiBand",
    ),
)
