"""Custom menu widget for the CAPS Noisegate plugin.

Control ports (from the plugin TTL):
  open    dB threshold to open the gate   (-60 .. 0,    default -45)
  attack  attack time in ms               (  0 .. 5,    default   0)
  close   dB threshold to close the gate  (-80 .. 0,    default -67.5)
  mains   mains frequency in Hz, 0 = auto (  0 .. 100,  default  50)
"""

from __future__ import annotations

from plugins.multiband_menu import MultibandWindow, ParamSlot


class CapsNoisegateWindow(MultibandWindow):
    def build_slots(self):
        return [
            ParamSlot("open", "Open", display_fn=self._fmt_db),
            ParamSlot("close", "Close", display_fn=self._fmt_db),
            ParamSlot("attack", "Attack", display_fn=self._fmt_ms),
            ParamSlot("mains", "Mains", display_fn=self._fmt_hz),
        ]

    @staticmethod
    def _fmt_db(value: float) -> str:
        return f"{value:+.0f}dB"

    @staticmethod
    def _fmt_ms(value: float) -> str:
        return f"{value:.0f}ms"

    @staticmethod
    def _fmt_hz(value: float) -> str:
        if value == 0.0:
            return "auto"
        return f"{value:.0f}Hz"