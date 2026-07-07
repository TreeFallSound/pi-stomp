"""LoopJefe multitrack looper plugin customization.

Declarative footswitch-LED spec only: state colors + loop-downbeat tint,
interpreted by the handler's generic LED driver (modalapi/led_render.py).
Momentary press semantics come for free from `advance`/`reset` being
`pprops:trigger` ports (common/parameter.py) — no plugin-specific input code.
"""

from __future__ import annotations

from modalapi.plugin_customization import LedSpec, PluginCustomization
from plugins.customization import register

LOOPJEFE_URIS = (
    "http://treefallsound.com/plugins/loopjefe",
    "http://treefallsound.com/plugins/loopjefe-2x2",
)

# LoopJefePlugin state values (../loopjefe-lv2/src/types.h)
_STATE_EMPTY = 0
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

_LOOPJEFE_LED_SPEC = LedSpec(
    state_symbol="state",
    colors=_STATE_COLORS,
    pulse=True,
    off_states=frozenset({_STATE_EMPTY}),
    steady_states=frozenset({_STATE_STOPPED}),
    downbeat_symbol="measure_number",
    downbeat_tint=60,
)

register(
    *LOOPJEFE_URIS,
    customization=PluginCustomization(
        display_name="LoopJefe",
        led_spec=_LOOPJEFE_LED_SPEC,
    ),
)
