"""Custom menu widget for the mod-mda-MultiBand plugin."""

from __future__ import annotations

from plugins.multiband_menu import MultibandWindow, ParamSlot
from uilib.misc import fmt_hz
from common.parameter import Symbol


class MdaMultiBandWindow(MultibandWindow):
    def build_slots(self):
        return [
            ParamSlot(Symbol("l_m"), "L↔M", display_fn=fmt_hz),
            ParamSlot(Symbol("m_h"), "M↔H", display_fn=fmt_hz),
            ParamSlot(Symbol("l_comp"), "L Comp"),
            ParamSlot(Symbol("m_comp"), "M Comp"),
            ParamSlot(Symbol("h_comp"), "H Comp"),
            ParamSlot(Symbol("l_out"), "L Out"),
            ParamSlot(Symbol("m_out"), "M Out"),
            ParamSlot(Symbol("h_out"), "H Out"),
        ]
