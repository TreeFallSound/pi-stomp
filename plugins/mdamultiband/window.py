"""Custom menu widget for the mod-mda-MultiBand plugin."""

from __future__ import annotations

from plugins.multiband_menu import MultibandWindow, ParamSlot
from uilib.misc import fmt_hz
from common.parameter import Symbol


class MdaMultiBandWindow(MultibandWindow):
    def build_slots(self):
        return [
            ParamSlot(Symbol("l_m"), "L↔M", (255, 180, 80), display_fn=fmt_hz),
            ParamSlot(Symbol("m_h"), "M↔H", (210, 130, 230), display_fn=fmt_hz),
            ParamSlot(Symbol("l_comp"), "L Comp", (255, 230, 80)),
            ParamSlot(Symbol("m_comp"), "M Comp", (130, 220, 110)),
            ParamSlot(Symbol("h_comp"), "H Comp", (110, 200, 230)),
            ParamSlot(Symbol("l_out"), "L Out", (200, 200, 200)),
            ParamSlot(Symbol("m_out"), "M Out", (180, 180, 180)),
            ParamSlot(Symbol("h_out"), "H Out", (160, 160, 160)),
        ]
