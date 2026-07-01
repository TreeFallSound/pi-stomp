"""Custom menu widget for the DISTRHO 3 Band Splitter plugin."""

from __future__ import annotations

from plugins.multiband_menu import MultibandWindow, ParamSlot
from uilib.misc import fmt_hz


class ThreeBandSplitterWindow(MultibandWindow):
    def build_slots(self):
        return [
            ParamSlot("low", "Low", (255, 180, 80)),
            ParamSlot("mid", "Mid", (255, 230, 80)),
            ParamSlot("high", "High", (130, 220, 110)),
            ParamSlot("master", "Master", (200, 200, 200)),
            ParamSlot("low_mid", "L↔M", (110, 200, 230), display_fn=fmt_hz),
            ParamSlot("mid_high", "M↔H", (210, 130, 230), display_fn=fmt_hz),
        ]
