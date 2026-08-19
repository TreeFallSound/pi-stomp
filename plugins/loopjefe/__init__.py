"""LoopJefe multitrack looper plugin customization.

Declarative footswitch-LED spec only: state colors + loop-downbeat tint,
interpreted by the handler's generic LED driver (modalapi/led_render.py).
Momentary press semantics come for free from `advance`/`reset` being
`pprops:trigger` ports (common/parameter.py) — no plugin-specific input code.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from modalapi.plugin_customization import LedSpec, PluginCustomization
from plugins.customization import register

if TYPE_CHECKING:
    from modalapi.plugin import Plugin

LOOPJEFE_URIS = (
    "http://treefallsound.com/plugins/loopjefe",
    "http://treefallsound.com/plugins/loopjefe-2x2",
)

# LoopJefePlugin state values (../loopjefe-lv2/src/types.h)
_STATE_EMPTY = 0
_STATE_RECORDING = 2
_STATE_RECORD_CLOSE = 3
_STATE_STOPPED = 5

_STATE_COLORS: dict[int, tuple[int, int, int]] = {
    1: (0, 80, 255),    # Record Arm
    2: (255, 0, 0),     # Recording
    3: (0, 80, 255),    # Record Close
    4: (0, 255, 0),     # Playback
    _STATE_STOPPED: (80, 80, 80),
    6: (0, 80, 255),    # Overdub Arm
    7: (255, 140, 0),   # Overdub
    8: (0, 80, 255),    # Overdub Close
}

# Short enough for a 320px/4 footswitch slot; the TTL scalePoints spell them
# out in full ("Record Arm", "Overdub Close").
_STATE_LABELS: dict[int, str] = {
    _STATE_EMPTY: "——",
    1: "Arm",
    2: "Rec",
    3: "Close",
    4: "Play",
    _STATE_STOPPED: "Stop",
    6: "Arm",
    7: "Dub",
    8: "Close",
}

_LOOPJEFE_LED_SPEC = LedSpec(
    state_symbol="state",
    colors=_STATE_COLORS,
    labels=_STATE_LABELS,
    pulse=True,
    off_states=frozenset({_STATE_EMPTY}),
    steady_states=frozenset({_STATE_STOPPED}),
    downbeat_symbol="measure_number",
    downbeat_tint=60,
    bars_symbol="loop_bars",
    # The initial take has no length yet to be a fraction of, so the progress
    # border sweeps instead of filling. Record Arm is excluded: nothing is
    # being captured, so nothing should move.
    chase_states=frozenset({_STATE_RECORDING, _STATE_RECORD_CLOSE}),
)

def _track_name(plugin: "Plugin") -> str | None:
    """"Loop 2", not "LoopJefe" — every track is the same plugin, so the
    instance number is the only thing that tells two switches apart."""
    match = re.search(r"(\d+)$", plugin.instance_id)
    return f"Loop {match.group(1)}" if match else None


register(
    *LOOPJEFE_URIS,
    customization=PluginCustomization(
        display_name="LoopJefe",
        display_name_fn=_track_name,
        led_spec=_LOOPJEFE_LED_SPEC,
        loop_icon=True,
    ),
)
