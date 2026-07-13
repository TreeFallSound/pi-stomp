"""Custom menu widget for the mod-caps-Eq10X2 plugin."""

from __future__ import annotations

from plugins.multiband_menu import MultibandWindow, ParamSlot


class CapsEq10X2Window(MultibandWindow):
    def build_slots(self):
        return [
            ParamSlot("band31hz", "31 Hz"),
            ParamSlot("band63hz", "63 Hz"),
            ParamSlot("band125hz", "125 Hz"),
            ParamSlot("band250hz", "250 Hz"),
            ParamSlot("band500hz", "500 Hz"),
            ParamSlot("band1khz", "1 kHz"),
            ParamSlot("band2khz", "2 kHz"),
            ParamSlot("band4khz", "4 kHz"),
            ParamSlot("band8khz", "8 kHz"),
            ParamSlot("band16khz", "16 kHz"),
        ]
