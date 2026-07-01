"""Registration for the mod-mda-Bandisto plugin."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.mdabandisto.window import MdaBandistoWindow

MDA_BANDISTO_URI = "http://moddevices.com/plugins/mda/Bandisto"

register(
    MDA_BANDISTO_URI,
    customization=PluginCustomization(
        panel_cls=MdaBandistoWindow,
        display_name="MDA Bandisto",
    ),
)
