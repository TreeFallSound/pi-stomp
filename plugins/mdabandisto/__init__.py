"""Registration for the mod-mda-Bandisto plugin."""

from __future__ import annotations

from common.parameter import Symbol
from modalapi.plugin_customization import PinnedParam
from plugins.customization import PluginCustomization, register
from uilib.misc import fmt_hz

MDA_BANDISTO_URI = "http://moddevices.com/plugins/mda/Bandisto"

register(
    MDA_BANDISTO_URI,
    customization=PluginCustomization(
        display_name="MDA Bandisto",
        pinned_params=(
            PinnedParam(Symbol("l_m"), "L↔M", display_fn=fmt_hz),
            PinnedParam(Symbol("m_h"), "M↔H", display_fn=fmt_hz),
            PinnedParam(Symbol("l_dist"), "L Dist"),
            PinnedParam(Symbol("m_dist"), "M Dist"),
            PinnedParam(Symbol("h_dist"), "H Dist"),
            PinnedParam(Symbol("l_out"), "L Out"),
            PinnedParam(Symbol("m_out"), "M Out"),
            PinnedParam(Symbol("h_out"), "H Out"),
        ),
    ),
)
