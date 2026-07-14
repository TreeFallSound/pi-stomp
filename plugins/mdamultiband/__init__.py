"""Registration for the mod-mda-MultiBand plugin."""

from __future__ import annotations

from common.parameter import Symbol
from modalapi.plugin_customization import PinnedParam
from plugins.customization import PluginCustomization, register
from uilib.misc import fmt_hz

MDA_MULTIBAND_URI = "http://moddevices.com/plugins/mda/MultiBand"

register(
    MDA_MULTIBAND_URI,
    customization=PluginCustomization(
        display_name="MDA MultiBand",
        pinned_params=(
            PinnedParam(Symbol("l_m"), "L↔M", display_fn=fmt_hz),
            PinnedParam(Symbol("m_h"), "M↔H", display_fn=fmt_hz),
            PinnedParam(Symbol("l_comp"), "L Comp"),
            PinnedParam(Symbol("m_comp"), "M Comp"),
            PinnedParam(Symbol("h_comp"), "H Comp"),
            PinnedParam(Symbol("l_out"), "L Out"),
            PinnedParam(Symbol("m_out"), "M Out"),
            PinnedParam(Symbol("h_out"), "H Out"),
        ),
    ),
)
