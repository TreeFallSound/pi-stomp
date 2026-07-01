from __future__ import annotations

from plugins.multiband_menu import MultibandWindow, ParamSlot


class SystemCompressorWindow(MultibandWindow):
    def build_slots(self):
        return [
            ParamSlot("COMP_MODE", "Mode", (255, 180, 80), display_fn=self._fmt_mode),
            ParamSlot("RELEASE", "Release", (130, 220, 110), display_fn=lambda v: f"{v:.0f}ms"),
            ParamSlot("MASTER_VOL", "Volume", (110, 200, 230), display_fn=lambda v: f"{v:+.0f}dB"),
        ]

    @staticmethod
    def _fmt_mode(v: float) -> str:
        return {1: "Light", 2: "Mild", 3: "Heavy"}.get(int(v), f"{v:.0f}")
