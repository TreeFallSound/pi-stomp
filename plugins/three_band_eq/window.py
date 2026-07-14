"""Custom menu widget for the DISTRHO 3 Band EQ plugin."""

from __future__ import annotations

from plugins.multiband_menu import MultibandWindow, ParamSlot
from uilib.misc import fmt_hz
from common.parameter import Symbol


class ThreeBandEqWindow(MultibandWindow):
    def build_slots(self):
        return [
            ParamSlot(Symbol("low"), "Low", (255, 180, 80)),
            ParamSlot(Symbol("mid"), "Mid", (255, 230, 80)),
            ParamSlot(Symbol("high"), "High", (130, 220, 110)),
            ParamSlot(Symbol("master"), "Master", (200, 200, 200)),
            ParamSlot(Symbol("low_mid"), "L↔M", (110, 200, 230), display_fn=fmt_hz),
            ParamSlot(Symbol("mid_high"), "M↔H", (210, 130, 230), display_fn=fmt_hz),
        ]
