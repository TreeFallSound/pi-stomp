"""Custom menu widget for the mod-caps-Eq10X2 plugin."""

from __future__ import annotations

from plugins.multiband_menu import CustomMenuWidget, ParamSlot


class CapsEq10X2MenuWidget(CustomMenuWidget):
    def build_slots(self):
        return [
            ParamSlot("band31hz", "31 Hz", (255, 80, 80)),
            ParamSlot("band63hz", "63 Hz", (255, 140, 80)),
            ParamSlot("band125hz", "125 Hz", (255, 200, 80)),
            ParamSlot("band250hz", "250 Hz", (220, 255, 80)),
            ParamSlot("band500hz", "500 Hz", (160, 255, 80)),
            ParamSlot("band1khz", "1 kHz", (100, 255, 120)),
            ParamSlot("band2khz", "2 kHz", (80, 220, 200)),
            ParamSlot("band4khz", "4 kHz", (80, 160, 255)),
            ParamSlot("band8khz", "8 kHz", (120, 100, 255)),
            ParamSlot("band16khz", "16 kHz", (200, 80, 255)),
        ]
