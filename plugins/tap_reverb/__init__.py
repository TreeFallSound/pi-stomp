"""Registration for the TAP Reverberator plugin."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.tap_reverb.panel import TapReverbPanel

TAP_REVERB_URI = "http://moddevices.com/plugins/tap/reverb"

register(
    TAP_REVERB_URI,
    customization=PluginCustomization(
        panel_cls=TapReverbPanel,
        display_name="TAP Reverberator",
    ),
)