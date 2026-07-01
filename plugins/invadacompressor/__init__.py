"""Invada compressor: mono and stereo share LV2 ports; both get the a-comp-derived panel."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.invadacompressor.panel import InvadaCompressorPanel

INVADA_COMPRESSOR_MONO_URI = "http://invadarecords.com/plugins/lv2/compressor/mono"
INVADA_COMPRESSOR_STEREO_URI = "http://invadarecords.com/plugins/lv2/compressor/stereo"

_customization = PluginCustomization(
    panel_cls=InvadaCompressorPanel,
    display_name="Invada Compressor",
)

register(INVADA_COMPRESSOR_MONO_URI, customization=_customization)
register(INVADA_COMPRESSOR_STEREO_URI, customization=_customization)
