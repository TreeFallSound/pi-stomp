"""Custom menu widget for the mod-mda-MultiBand plugin."""

from __future__ import annotations

from plugins.multiband_menu import MultibandWindow, ParamSlot
from uilib.misc import fmt_hz


class MdaMultiBandWindow(MultibandWindow):
    def build_slots(self):
        return [
            ParamSlot("l_m", "L↔M", (255, 180, 80), display_fn=fmt_hz),
            ParamSlot("m_h", "M↔H", (210, 130, 230), display_fn=fmt_hz),
            ParamSlot("l_comp", "L Comp", (255, 230, 80)),
            ParamSlot("m_comp", "M Comp", (130, 220, 110)),
            ParamSlot("h_comp", "H Comp", (110, 200, 230)),
            ParamSlot("l_out", "L Out", (200, 200, 200)),
            ParamSlot("m_out", "M Out", (180, 180, 180)),
            ParamSlot("h_out", "H Out", (160, 160, 160)),
        ]
