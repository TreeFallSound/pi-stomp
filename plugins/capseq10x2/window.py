"""Custom menu widget for the mod-caps-Eq10X2 plugin."""

from __future__ import annotations

from plugins.multiband_menu import MultibandWindow, ParamSlot
from common.parameter import Symbol


class CapsEq10X2Window(MultibandWindow):
    def build_slots(self):
        return [
            ParamSlot(Symbol("band31hz"), "31 Hz"),
            ParamSlot(Symbol("band63hz"), "63 Hz"),
            ParamSlot(Symbol("band125hz"), "125 Hz"),
            ParamSlot(Symbol("band250hz"), "250 Hz"),
            ParamSlot(Symbol("band500hz"), "500 Hz"),
            ParamSlot(Symbol("band1khz"), "1 kHz"),
            ParamSlot(Symbol("band2khz"), "2 kHz"),
            ParamSlot(Symbol("band4khz"), "4 kHz"),
            ParamSlot(Symbol("band8khz"), "8 kHz"),
            ParamSlot(Symbol("band16khz"), "16 kHz"),
        ]
