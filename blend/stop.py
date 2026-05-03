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

"""BlendStop class and related utilities for blend mode."""

import logging

from blend.types import (
    DiffMapDict,
    EnrichedDiffMap,
    MidiBoundParams,
    ParamData,
    ParameterTypeGetter,
    SnapshotStateDict,
)
from modalapi.parameter import Type as ParameterType


class BlendStop:
    """
    Represents a gradient stop in the blend interpolation space.
    """

    def __init__(self, position: float, snapshot_index: int, snapshot_state: SnapshotStateDict) -> None:
        """
        Initialize a blend stop.

        Args:
            position: float (0.0-1.0), position in global interpolation space
            snapshot_index: int, which snapshot this represents
            snapshot_state: dict, captured parameter states
                Format: {instance_id: {symbol: value}}
                Example: {"/BigMuffPi": {"Tone": 0.35, "Level": 0.72}}
        """
        self.position: float = position
        self.snapshot_index: int = snapshot_index
        self.snapshot_state: SnapshotStateDict = snapshot_state

    def __repr__(self) -> str:
        param_count = sum(len(params) for params in self.snapshot_state.values())
        return f"BlendStop(pos={self.position:.2f}, snap={self.snapshot_index}, params={param_count})"

    @staticmethod
    def build_diff_map(
        state_a: SnapshotStateDict, state_b: SnapshotStateDict, param_type_getter: ParameterTypeGetter
    ) -> DiffMapDict:
        """
        Build map of parameters that differ between two states.

        Args:
            state_a: State dict from snapshot A {instance_id: {symbol: value}}
            state_b: State dict from snapshot B {instance_id: {symbol: value}}
            param_type_getter: Function(instance_id, symbol) -> ParameterType

        Returns:
            Dict: {instance_id: {symbol: (val_a, val_b, param_type)}}
        """
        diff_map = {}

        # Get all instance_ids from both states
        all_instances = set(state_a.keys()) | set(state_b.keys())

        for instance_id in all_instances:
            params_a = state_a.get(instance_id, {})
            params_b = state_b.get(instance_id, {})

            # Get all parameter symbols
            all_symbols = set(params_a.keys()) | set(params_b.keys())

            for symbol in all_symbols:
                val_a = params_a.get(symbol, 0.0)
                val_b = params_b.get(symbol, 0.0)

                # Only include if values differ
                if val_a != val_b:
                    # Get parameter type
                    param_type = param_type_getter(instance_id, symbol)

                    if instance_id not in diff_map:
                        diff_map[instance_id] = {}

                    diff_map[instance_id][symbol] = (val_a, val_b, param_type)

        return diff_map

    @staticmethod
    def adjust_binary_params(diff_map: DiffMapDict) -> DiffMapDict:
        """
        Apply "on wins" logic to binary parameters.

        If either value is 1.0 (on), set both to 1.0.
        If both are 0.0 (off), set both to 0.0.

        Args:
            diff_map: Parameter diff map {instance_id: {symbol: (val_a, val_b, param_type)}}

        Returns:
            Adjusted diff map with same structure
        """
        adjusted: DiffMapDict = {}

        for instance_id, params in diff_map.items():
            adjusted[instance_id] = {}

            for symbol, (val_a, val_b, param_type) in params.items():
                # Check if binary parameter (TOGGLED type or :bypass)
                is_binary = param_type == ParameterType.TOGGLED or symbol == ":bypass"

                if is_binary:
                    val_a = val_b = max(val_a, val_b)

                adjusted[instance_id][symbol] = (val_a, val_b, param_type)

        return adjusted

    @staticmethod
    def build_enriched_diff_map(
        lower_stop: "BlendStop",
        upper_stop: "BlendStop",
        param_type_getter: ParameterTypeGetter,
        midi_bound_params: MidiBoundParams | None = None,
    ) -> EnrichedDiffMap:
        """
        Build diff map of parameters that differ between two stops.

        Args:
            lower_stop: Lower stop of segment
            upper_stop: Upper stop of segment
            param_type_getter: Function to get parameter type
            midi_bound_params: Set of (instance_id, symbol) tuples for MIDI-bound params to exclude

        Returns:
            Enriched diff map: {instance_id: {symbol: ParamData}}
        """
        diff_map = BlendStop.build_diff_map(lower_stop.snapshot_state, upper_stop.snapshot_state, param_type_getter)
        diff_map = BlendStop.adjust_binary_params(diff_map)

        if midi_bound_params:
            for instance_id in list(diff_map.keys()):
                for symbol in list(diff_map[instance_id].keys()):
                    if (instance_id, symbol) in midi_bound_params:
                        del diff_map[instance_id][symbol]
                        logging.debug(f"Excluding MIDI-bound parameter: {instance_id}/{symbol}")
                if not diff_map[instance_id]:
                    del diff_map[instance_id]

        enriched: EnrichedDiffMap = {}
        for instance_id, params in diff_map.items():
            enriched[instance_id] = {}
            for symbol, (val_a, val_b, param_type) in params.items():
                enriched[instance_id][symbol] = ParamData(val_a=val_a, val_b=val_b, param_type=param_type)

        return enriched
