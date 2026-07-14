from __future__ import annotations

from plugins.multiband_menu import MultibandWindow, ParamSlot
from common.parameter import Symbol


class SystemCompressorWindow(MultibandWindow):
    def build_slots(self):
        return [
            ParamSlot(Symbol("COMP_MODE"), "Mode", display_fn=self._fmt_mode),
            ParamSlot(Symbol("RELEASE"), "Release", display_fn=lambda v: f"{v:.0f}ms"),
            ParamSlot(Symbol("MASTER_VOL"), "Volume", display_fn=lambda v: f"{v:+.0f}dB"),
        ]

    @staticmethod
    def _fmt_mode(v: float) -> str:
        return {1: "Light", 2: "Mild", 3: "Heavy"}.get(int(v), f"{v:.0f}")
