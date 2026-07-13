"""Custom menu widget for the mod-mda-MultiBand plugin."""

from __future__ import annotations

from plugins.multiband_menu import MultibandWindow, ParamSlot
from uilib.misc import fmt_hz


class MdaMultiBandWindow(MultibandWindow):
    def build_slots(self):
        return [
            ParamSlot("l_m", "L↔M", display_fn=fmt_hz),
            ParamSlot("m_h", "M↔H", display_fn=fmt_hz),
            ParamSlot("l_comp", "L Comp"),
            ParamSlot("m_comp", "M Comp"),
            ParamSlot("h_comp", "H Comp"),
            ParamSlot("l_out", "L Out"),
            ParamSlot("m_out", "M Out"),
            ParamSlot("h_out", "H Out"),
        ]
