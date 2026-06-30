"""Custom menu widget for the DISTRHO 3 Band EQ plugin."""

from __future__ import annotations

from plugins.multiband_menu import CustomMenuWidget, ParamSlot


class ThreeBandEqMenuWidget(CustomMenuWidget):
    def build_slots(self):
        return [
            ParamSlot("low", "Low", (255, 180, 80)),
            ParamSlot("mid", "Mid", (255, 230, 80)),
            ParamSlot("high", "High", (130, 220, 110)),
            ParamSlot("master", "Master", (200, 200, 200)),
            ParamSlot("low_mid", "L↔M", (110, 200, 230), display_fn=self._fmt_hz),
            ParamSlot("mid_high", "M↔H", (210, 130, 230), display_fn=self._fmt_hz),
        ]

    @staticmethod
    def _fmt_hz(value: float) -> str:
        if value >= 1000.0:
            return f"{value / 1000.0:.1f}k"
        return f"{value:.0f}"
