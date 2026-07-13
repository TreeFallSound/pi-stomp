"""Custom menu widget for the mod-mda-Bandisto plugin."""

from __future__ import annotations

from plugins.multiband_menu import MultibandWindow, ParamSlot
from uilib.misc import fmt_hz


class MdaBandistoWindow(MultibandWindow):
    def build_slots(self):
        return [
            ParamSlot("l_m", "L↔M", display_fn=fmt_hz),
            ParamSlot("m_h", "M↔H", display_fn=fmt_hz),
            ParamSlot("l_dist", "L Dist"),
            ParamSlot("m_dist", "M Dist"),
            ParamSlot("h_dist", "H Dist"),
            ParamSlot("l_out", "L Out"),
            ParamSlot("m_out", "M Out"),
            ParamSlot("h_out", "H Out"),
        ]
