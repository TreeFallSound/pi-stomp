"""Registration for the mod-mda-Bandisto plugin."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.mdabandisto.menu_widget import MdaBandistoMenuWidget

MDA_BANDISTO_URI = "http://moddevices.com/plugins/mda/Bandisto"

register(
    MDA_BANDISTO_URI,
    customization=PluginCustomization(
        menu_widget_cls=MdaBandistoMenuWidget,
        display_name="MDA Bandisto",
    ),
)
