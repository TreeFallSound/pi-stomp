"""LoopJefe multitrack looper plugin customization.

Registers footswitch behavior for loopjefe-lv2: momentary short-press
semantics, output_set subscriptions for state and measure_number, and
per-tick LED rendering (state color + beat pulse).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from modalapi.footswitch_behavior import LedDisplayStyle
from modalapi.plugin import Plugin
from plugins.customization import PluginCustomization, register

if TYPE_CHECKING:
    from pistomp.beatsync import TickState


LOOPJEFE_URIS = (
    "http://treefallsound.com/plugins/loopjefe",
    "http://treefallsound.com/plugins/loopjefe-2x2",
)

_STATE_COLORS: dict[int, tuple[int, int, int]] = {
    1: (0, 80, 255),    # Record Arm
    2: (255, 0, 0),     # Recording
    3: (0, 80, 255),    # Record Close
    4: (0, 255, 0),     # Playback
    6: (0, 80, 255),    # Overdub Arm
    7: (255, 140, 0),   # Overdub
    8: (0, 80, 255),    # Overdub Close
}

_DOWNBEAT_TINT = 60  # added to each channel for the loop-downbeat variant


def _brighten(c: tuple[int, int, int]) -> tuple[int, int, int]:
    return (min(255, c[0] + _DOWNBEAT_TINT), min(255, c[1] + _DOWNBEAT_TINT), min(255, c[2] + _DOWNBEAT_TINT))


class LoopjefeBehavior:
    def __init__(self, plugin: Plugin) -> None:
        self._instance_id = plugin.instance_id
        self._state: int = 0
        self._measure_number: int = 0

    @property
    def momentary(self) -> bool:
        return True

    def output_subscriptions(self) -> Iterable[str]:
        return ("state", "measure_number")

    def on_output(self, symbol: str, value: float) -> None:
        if symbol == "state":
            self._state = int(value)
        elif symbol == "measure_number":
            self._measure_number = int(value)

    def led_color(self, beat: TickState) -> tuple[int, int, int] | None:
        if self._state == 0:
            return None
        if self._state == 5:
            return (80, 80, 80)
        base = _STATE_COLORS.get(self._state, (80, 80, 80))
        if self._measure_number == 0:
            return _brighten(base)
        return base

    def led_style(self, beat: TickState) -> LedDisplayStyle:
        if self._state == 0 or self._state == 5:
            return LedDisplayStyle.SOLID
        return LedDisplayStyle.METRONOME


def make_loopjefe_behavior(plugin: Plugin) -> LoopjefeBehavior:
    return LoopjefeBehavior(plugin)


register(
    *LOOPJEFE_URIS,
    customization=PluginCustomization(
        display_name="LoopJefe",
        footswitch_behavior_fn=make_loopjefe_behavior,
    ),
)
