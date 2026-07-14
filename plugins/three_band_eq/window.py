"""Custom menu widget for the DISTRHO 3 Band EQ plugin."""

from __future__ import annotations

from plugins.multiband_menu import MultibandWindow, ParamSlot
from uilib.misc import fmt_hz
from common.parameter import Symbol


class ThreeBandEqWindow(MultibandWindow):
    def build_slots(self):
        return [
            ParamSlot(Symbol("low"), "Low"),
            ParamSlot(Symbol("mid"), "Mid"),
            ParamSlot(Symbol("high"), "High"),
            ParamSlot(Symbol("master"), "Master"),
            ParamSlot(Symbol("low_mid"), "L↔M", display_fn=fmt_hz),
            ParamSlot(Symbol("mid_high"), "M↔H", display_fn=fmt_hz),
        ]
