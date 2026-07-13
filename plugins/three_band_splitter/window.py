"""Custom menu widget for the DISTRHO 3 Band Splitter plugin."""

from __future__ import annotations

from plugins.multiband_menu import MultibandWindow, ParamSlot
from uilib.misc import fmt_hz


class ThreeBandSplitterWindow(MultibandWindow):
    def build_slots(self):
        return [
            ParamSlot("low", "Low"),
            ParamSlot("mid", "Mid"),
            ParamSlot("high", "High"),
            ParamSlot("master", "Master"),
            ParamSlot("low_mid", "L↔M", display_fn=fmt_hz),
            ParamSlot("mid_high", "M↔H", display_fn=fmt_hz),
        ]
