"""Registration for the mod-mda-MultiBand plugin."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.mdamultiband.menu_widget import MdaMultiBandMenuWidget

MDA_MULTIBAND_URI = "http://moddevices.com/plugins/mda/MultiBand"

register(
    MDA_MULTIBAND_URI,
    customization=PluginCustomization(
        menu_widget_cls=MdaMultiBandMenuWidget,
        display_name="MDA MultiBand",
    ),
)
