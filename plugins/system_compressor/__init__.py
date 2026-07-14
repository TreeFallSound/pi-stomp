"""System Compressor: pinned arc rings (mode/release/volume).

A full compressor panel (graph + GR meter) doesn't make sense here because
this plugin has no threshold, ratio, or knee ports — it's a streamlined
end-of-chain compressor with just mode/release/volume.
"""

from __future__ import annotations

from common.parameter import Symbol
from modalapi.plugin_customization import PinnedParam
from plugins.customization import PluginCustomization, register

SYSTEM_COMPRESSOR_URI = "http://moddevices.com/plugins/mod-devel/System-Compressor"

_MODES = {1: "Light", 2: "Mild", 3: "Heavy"}


def _fmt_mode(value: float) -> str:
    return _MODES.get(int(value), f"{value:.0f}")


def _fmt_ms(value: float) -> str:
    return f"{value:.0f}ms"


def _fmt_db(value: float) -> str:
    return f"{value:+.0f}dB"


register(
    SYSTEM_COMPRESSOR_URI,
    customization=PluginCustomization(
        display_name="System Compressor",
        pinned_params=(
            PinnedParam(Symbol("COMP_MODE"), "Mode", display_fn=_fmt_mode),
            PinnedParam(Symbol("RELEASE"), "Release", display_fn=_fmt_ms),
            PinnedParam(Symbol("MASTER_VOL"), "Volume", display_fn=_fmt_db),
        ),
    ),
)
