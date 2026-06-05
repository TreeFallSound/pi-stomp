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

"""BlendStop dataclass and segment diff-map builder."""

import logging
from dataclasses import dataclass, field

from blend.types import (
    EnrichedDiffMap,
    MidiBoundParams,
    ParamData,
    ParameterTypeGetter,
    SnapshotStateDict,
    Symbol,
)
from modalapi.parameter import Type as ParameterType


@dataclass
class BlendStop:
    """A gradient stop in the blend interpolation space."""

    position: float
    snapshot_index: int
    snapshot_state: SnapshotStateDict = field(default_factory=dict)

    def __repr__(self) -> str:
        param_count = sum(len(params) for params in self.snapshot_state.values())
        return f"BlendStop(pos={self.position:.2f}, snap={self.snapshot_index}, params={param_count})"


def _is_binary(symbol: Symbol, param_type: ParameterType) -> bool:
    return param_type == ParameterType.TOGGLED or symbol == ":bypass"


def build_segment_diff_map(
    lower: BlendStop,
    upper: BlendStop,
    param_type_getter: ParameterTypeGetter,
    midi_bound_params: MidiBoundParams | None = None,
) -> EnrichedDiffMap:
    """Build a diff map of parameters that differ between two stops.

    Binary parameters (TOGGLED, ":bypass") use "on wins" — if either side is 1.0,
    both endpoints become 1.0 so any interpolation in the segment stays on.
    MIDI-bound parameters are skipped to avoid conflicts with the blend input.
    """
    state_a, state_b = lower.snapshot_state, upper.snapshot_state
    skip = midi_bound_params or set()
    diff: EnrichedDiffMap = {}

    for instance_id in state_a.keys() | state_b.keys():
        params_a = state_a.get(instance_id, {})
        params_b = state_b.get(instance_id, {})
        per_plugin: dict[Symbol, ParamData] = {}

        for symbol in params_a.keys() | params_b.keys():
            if (instance_id, symbol) in skip:
                logging.debug(f"Excluding MIDI-bound parameter: {instance_id}/{symbol}")
                continue

            val_a = params_a.get(symbol, 0.0)
            val_b = params_b.get(symbol, 0.0)
            if val_a == val_b:
                continue

            param_type = param_type_getter(instance_id, symbol)
            if _is_binary(symbol, param_type):
                # "on wins": collapse to a constant 1.0 segment (still in diff map,
                # so it's resent on activation regardless of lerp position).
                val_a = val_b = max(val_a, val_b)

            per_plugin[symbol] = ParamData(val_a=val_a, val_b=val_b, param_type=param_type)

        if per_plugin:
            diff[instance_id] = per_plugin

    return diff
