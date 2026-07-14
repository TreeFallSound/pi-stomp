"""Registration for the CAPS Noisegate plugin.

Control ports (from the plugin TTL):
  open    dB threshold to open the gate   (-60 .. 0,    default -45)
  attack  attack time in ms               (  0 .. 5,    default   0)
  close   dB threshold to close the gate  (-80 .. 0,    default -67.5)
  mains   mains frequency in Hz, 0 = auto (  0 .. 100,  default  50)
"""

from __future__ import annotations

from common.parameter import Symbol
from modalapi.plugin_customization import PinnedParam
from plugins.customization import PluginCustomization, register

CAPS_NOISEGATE_URI = "http://moddevices.com/plugins/caps/Noisegate"


def _fmt_db(value: float) -> str:
    return f"{value:+.0f}dB"


def _fmt_ms(value: float) -> str:
    return f"{value:.0f}ms"


def _fmt_mains(value: float) -> str:
    return "auto" if value == 0.0 else f"{value:.0f}Hz"


register(
    CAPS_NOISEGATE_URI,
    customization=PluginCustomization(
        display_name="CAPS Noisegate",
        pinned_params=(
            PinnedParam(Symbol("open"), "Open", display_fn=_fmt_db),
            PinnedParam(Symbol("close"), "Close", display_fn=_fmt_db),
            PinnedParam(Symbol("attack"), "Attack", display_fn=_fmt_ms),
            PinnedParam(Symbol("mains"), "Mains", display_fn=_fmt_mains),
        ),
    ),
)
