# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Generic, data-driven footswitch-LED rendering.

Pure function of (LedSpec, plugin.output_values) -> (color, style). No
footswitch, beat, or plugin-instance coupling — the per-tick brightness
envelope (pulse phase, downbeat emphasis) is applied uniformly by the
handler's single LED-writing helper, not here.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from common.loop_progress import LoopFill, LoopProgress

if TYPE_CHECKING:
    from modalapi.plugin_customization import LedSpec


_BEAT_DECAY = 0.7


class LedDisplayStyle(Enum):
    SOLID = auto()
    METRONOME = auto()


def render_led_spec(
    spec: LedSpec, output_values: dict[str, float]
) -> tuple[tuple[int, int, int] | None, LedDisplayStyle]:
    state = int(output_values.get(spec.state_symbol, 0))
    if state in spec.off_states:
        return None, LedDisplayStyle.SOLID
    base = spec.colors.get(state)
    if base is None:
        return None, LedDisplayStyle.SOLID
    if spec.downbeat_symbol is not None and int(output_values.get(spec.downbeat_symbol, -1)) == 0:
        base = (
            min(255, base[0] + spec.downbeat_tint),
            min(255, base[1] + spec.downbeat_tint),
            min(255, base[2] + spec.downbeat_tint),
        )
    style = LedDisplayStyle.METRONOME if (spec.pulse and state not in spec.steady_states) else LedDisplayStyle.SOLID
    return base, style


def metronome_brightness(beat_phase: float, is_bar_start: bool) -> float:
    """The per-beat brightness envelope: full on the downbeat, decaying across
    the beat. Shared by the physical LED and the LCD's progress border so a
    slot and its switch never pulse out of step."""
    if is_bar_start:
        return 1.0
    return 1.0 - beat_phase * _BEAT_DECAY


def state_label(spec: LedSpec, output_values: dict[str, float]) -> str | None:
    """Short display name for the current state, or None when the plugin
    declares no `labels`. Same lookup as `render_led_spec`, for the LCD."""
    if spec.labels is None:
        return None
    return spec.labels.get(int(output_values.get(spec.state_symbol, 0)))


def loop_progress(
    spec: LedSpec,
    output_values: dict[str, float],
    bar_phase: float,
    beat_brightness: float = 1.0,
) -> LoopProgress | None:
    """Where the plugin is through its loop, or None if it has no loop to be
    through. `bar_phase` interpolates within the current bar — the plugin only
    publishes a bar index, and a per-sample position port would be a monitored
    output changing every process cycle. `beat_brightness` is the envelope from
    `metronome_brightness`, applied only to the states the spec says pulse."""
    if spec.bars_symbol is None or spec.downbeat_symbol is None:
        return None
    color, style = render_led_spec(spec, output_values)
    if color is None:
        return None
    pulse = beat_brightness if style is LedDisplayStyle.METRONOME else 1.0

    state = int(output_values.get(spec.state_symbol, 0))
    bars = int(output_values.get(spec.bars_symbol, 0))
    measure = int(output_values.get(spec.downbeat_symbol, 0))

    # Past the length it declared (an overdub that outgrew the head loop) is
    # the same situation as a take still recording: a position, no denominator.
    if state in spec.chase_states or (bars > 0 and measure >= bars):
        return LoopProgress(LoopFill.CHASE, color, 0, bar_phase, pulse)
    if bars <= 0:
        return None
    if state in spec.steady_states:
        return LoopProgress(LoopFill.STATIC, color, bars)
    return LoopProgress(LoopFill.FILL, color, bars, (measure + bar_phase) / bars, pulse)
