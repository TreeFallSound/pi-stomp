"""Pedalboard-level transport controls (:bpm, :bpb, :rolling).

mod-ui addresses these through a /pedalboard pseudo-instance (id 9995) with
virtual port symbols. We mirror it as a synthetic Plugin whose URI is
``urn:mod:pedalboard`` so the customizer resolves it here. The label hook
supplies live-value text (♩=120, 4/4, Playing/Stopped) that the LCD renders
directly, bypassing shorten_name's lowercasing.
"""

from __future__ import annotations

from common.parameter import Parameter
from modalapi.plugin_customization import PluginCustomization
from modalapi.pedalboard import BPM_SYMBOL, BPB_SYMBOL, ROLLING_SYMBOL
from plugins.customization import register

TRANSPORT_URI = "urn:mod:pedalboard"


def _transport_label(param: Parameter) -> str:
    if param.symbol == BPM_SYMBOL:
        return f"♩={int(round(param.value))}"
    if param.symbol == BPB_SYMBOL:
        return f"{int(round(param.value))}/4"
    if param.symbol == ROLLING_SYMBOL:
        return "Playing" if param.value >= 0.5 else "Stopped"
    return param.name


register(
    TRANSPORT_URI,
    customization=PluginCustomization(
        control_label_fn=_transport_label,
    ),
)
