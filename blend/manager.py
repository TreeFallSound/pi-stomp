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

"""Main BlendMode coordinator class with pre-computation optimization."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from blend.easing import EASING_FUNCTIONS, EasingFunc
from blend.parameter_setter import ParameterSetter
from blend.input_controller import InputController
from blend.snapshot import SnapshotManager
from modalapi.pedalboard_monitor import FileChangeMonitor
from blend.stop import BlendStop
from blend.types import (
    BlendSnapshotConfig,
    EnrichedDiffMap,
    MidiBoundParams,
    NormalizedStops,
    StopData,
)
from modalapi.parameter import Type as ParameterType

if TYPE_CHECKING:
    from modalapi.modhandler import Modhandler




class BlendMode:
    """Coordinates blend mode components to enable smooth parameter interpolation."""

    def __init__(self, handler: Any, config: BlendSnapshotConfig) -> None:
        self.handler: Modhandler = handler
        self.config: BlendSnapshotConfig = config
        self.stops: list[BlendStop] = []
        self.segment_diff_maps: list[EnrichedDiffMap] = []

        # Components (initialized in initialize())
        self.parameter_setter: ParameterSetter | None = None
        self.input_controller: InputController | None = None

        self.snapshots_monitor: FileChangeMonitor | None = None

    def prepare(self) -> None:
        """
        Prepare blend mode (one-time setup when pedalboard loads).
        Pre-computes enriched diff maps for each segment at initialization
        to minimize work in the critical path (pedal movement).
        """
        logging.info("Preparing blend mode...")

        try:
            easing_func = self._validate_config()
            self.stops = self._create_stops()

            # Extract MIDI-bound parameters to exclude from interpolation
            midi_bound_params = self._extract_midi_bound_parameters()

            logging.info(f"Pre-computing diff maps for {len(self.stops) - 1} segments...")
            self.segment_diff_maps = []
            for segment_idx in range(len(self.stops) - 1):
                lower = self.stops[segment_idx]
                upper = self.stops[segment_idx + 1]

                diff_map = BlendStop.build_enriched_diff_map(
                    lower,
                    upper,
                    self._get_parameter_type,
                    midi_bound_params,
                )

                self.segment_diff_maps.append(diff_map)

                param_count = sum(len(params) for params in diff_map.values())
                logging.debug(
                    f"  Segment {segment_idx} ({lower.position:.2f} -> {upper.position:.2f}): "
                    f"{param_count} differing parameters"
                )

            self.parameter_setter = ParameterSetter(self.handler.ws_bridge)

            input_id = self.config.get("input_id")
            if input_id is None:
                raise ValueError("Blend mode requires 'input_id' config")

            # Initialize input controller (but don't attach yet)
            self.input_controller = InputController(
                easing_func,
                self.stops,
                self.segment_diff_maps,
                self.parameter_setter,
            )

            snapshots_path = Path(self.handler.current.pedalboard.bundle) / "snapshots.json"
            self.snapshots_monitor = FileChangeMonitor(str(snapshots_path))
            logging.info(f"Blend mode prepared with {len(self.stops)} stops")

        except Exception as e:
            logging.error(f"Failed to prepare blend mode: {e}")
            raise

    def activate(self) -> None:
        """
        Activate blend mode (attach to input).

        Called when switching to this blend snapshot. Clears de-duplication cache
        and syncs current input position to set all parameters (including bypass states).
        """
        if not self.input_controller:
            raise RuntimeError("Cannot activate - blend mode not prepared")

        input_id = self.config.get("input_id")
        if input_id is None:
            raise ValueError("Blend mode requires 'input_id' config")

        # Clear de-duplication cache so all parameters (including bypass) get sent fresh
        if self.parameter_setter:
            self.parameter_setter.reset_tracking()

        # Attach to analog input (expression pedal or encoder)
        self.input_controller.attach_to_input(
            self.handler.hardware.analog_controls, self.handler.hardware.encoders, input_id
        )

        # Immediately sync current input position to set all parameters
        # (blend snapshot is empty, so we need to establish initial state)
        try:
            self.input_controller.sync_current_position()
        except Exception as e:
            # If sync fails, detach to avoid leaving callback attached
            logging.error(f"Failed to sync blend mode position: {e}")
            self.input_controller.detach_from_input()
            raise

        logging.info(f"Activated blend mode: '{self.config.get('name')}'")

    def deactivate(self) -> None:
        """Deactivate blend mode (detach from input)."""
        if not self.input_controller:
            return

        # Clear any pending parameter updates to prevent stale messages
        if self.handler.ws_bridge:
            cleared = self.handler.ws_bridge.clear_queue()
            if cleared > 0:
                logging.debug(f"Cleared {cleared} pending WebSocket messages")

        # Detach from input
        self.input_controller.detach_from_input()

        # Reset tracking state
        if self.parameter_setter:
            self.parameter_setter.reset_tracking()

        logging.info(f"Deactivated blend mode: '{self.config.get('name')}'")

    def _normalize_stops_config(self, stops_config: dict[str, int | str] | list[str | int]) -> NormalizedStops:
        """
        Normalize stops configuration to dict format.

        Converts list format to dict with evenly spaced positions.
        Example: ["A", "B", "C"] → {"0.0": "A", "0.5": "B", "1.0": "C"}
        """
        if isinstance(stops_config, dict):
            return stops_config

        if isinstance(stops_config, list):
            if len(stops_config) < 2:
                raise ValueError("Stops list must have at least 2 entries")

            # Auto-space evenly across [0.0, 1.0]
            count = len(stops_config)
            step = 1.0 / (count - 1) if count > 1 else 0.0

            normalized_stops: NormalizedStops = {}
            for i, snapshot_id in enumerate(stops_config):
                position = i * step
                # Use 6 decimal places for precision
                normalized_stops[f"{position:.6f}"] = snapshot_id

            logging.debug(f"Normalized list stops to: {normalized_stops}")
            return normalized_stops

        raise ValueError(f"Stops must be dict or list, got {type(stops_config)}")

    def _extract_midi_bound_parameters(self) -> MidiBoundParams:
        """
        Extract all MIDI-bound parameters from current pedalboard.

        Scans all plugins in the pedalboard and collects parameters that have
        MIDI bindings. These parameters should be excluded from interpolation
        to avoid conflicts with the blend mode input.

        Returns:
            Set of (instance_id, symbol) tuples for MIDI-bound parameters
        """
        midi_params: set[tuple[str, str]] = set()
        pedalboard = self.handler.current.pedalboard

        for plugin in pedalboard.plugins:
            for symbol, param in plugin.parameters.items():
                if param.binding is not None:  # Format: "channel:CC"
                    midi_params.add((plugin.instance_id, symbol))
                    logging.debug(f"Found MIDI binding: {plugin.instance_id}/{symbol} -> {param.binding}")

        if midi_params:
            logging.info(f"Excluding {len(midi_params)} MIDI-bound parameters from blend interpolation")

        return midi_params

    def _validate_config(self) -> EasingFunc:
        easing_name = self.config.get("interpolation", "linear")
        easing_func = EASING_FUNCTIONS.get(easing_name)

        if not easing_func:
            raise ValueError(
                f"Invalid interpolation '{easing_name}', must be one of: {', '.join(EASING_FUNCTIONS.keys())}"
            )

        logging.debug(f"Config validated: interpolation={easing_name}")
        return easing_func

    def _create_stops(self) -> list[BlendStop]:
        """Load snapshots and create BlendStop objects from current config."""
        stops_config = self.config.get("stops")
        if not stops_config:
            raise ValueError("Blend mode requires 'stops' config")

        snapshot_stops = self._normalize_stops_config(stops_config)
        if len(snapshot_stops) < 2:
            raise ValueError(f"Blend mode requires at least 2 stops, got {len(snapshot_stops)}")

        # Read snapshots file
        bundle_path = Path(self.handler.current.pedalboard.bundle)
        snapshots_data = SnapshotManager.read_snapshots_file(bundle_path)

        stops_data: list[StopData] = []
        for position_str, snapshot_identifier in snapshot_stops.items():
            # Validate position is a stringified float
            try:
                position = float(position_str)
            except ValueError:
                raise ValueError(
                    f"Invalid position key '{position_str}': must be a stringified float (e.g., '0.0', '0.5')"
                )

            # Validate position is in range [0.0, 1.0]
            if position < 0.0 or position > 1.0:
                raise ValueError(f"Position {position} out of range: must be between 0.0 and 1.0")

            # Resolve snapshot identifier (index or name) to index
            snapshot_index = SnapshotManager.resolve_snapshot_identifier(snapshots_data, snapshot_identifier)

            stops_data.append(StopData(position, snapshot_index))

        stops_data.sort(key=lambda x: x.position)

        # Create BlendStop objects
        stops = []
        for stop_data in stops_data:
            state = SnapshotManager.parse_snapshot_data(snapshots_data, stop_data.snapshot_index)
            stop = BlendStop(stop_data.position, stop_data.snapshot_index, state)
            stops.append(stop)
            logging.debug(f"Created {stop}")

        # Validate we have at least 2 stops
        if len(stops) < 2:
            raise ValueError(f"Need at least 2 stops, got {len(stops)}")

        # Limit to 4 stops for practical reasons
        # (hermite/catmull-rom look 2 stops back/forward for context)
        if len(stops) > 4:
            logging.warning(f"Limiting to 4 stops (got {len(stops)})")
            stops = stops[:4]

        stops.sort(key=lambda s: s.position)
        for i in range(len(stops) - 1):
            pos_a = stops[i].position
            pos_b = stops[i + 1].position

            # Check positions are strictly increasing
            if pos_a >= pos_b:
                raise ValueError(
                    f"Stop positions must be strictly increasing: stop {i} at {pos_a}, stop {i + 1} at {pos_b}"
                )

            # Check positions map to different CC values (MIDI resolution check)
            cc_a = int(pos_a * 127)
            cc_b = int(pos_b * 127)
            if cc_a == cc_b:
                raise ValueError(
                    f"Stop positions too close - both map to CC {cc_a}: "
                    f"stop {i} at {pos_a}, stop {i + 1} at {pos_b}. "
                    f"Minimum separation is {1.0 / 127:.6f}"
                )

        return stops

    def _get_parameter_type(self, instance_id: str, symbol: str) -> ParameterType:
        # Find plugin by instance_id
        for plugin in self.handler.current.pedalboard.plugins:
            if plugin.instance_id == instance_id:
                param = plugin.parameters.get(symbol)
                if param:
                    return param.type

        # Default to DEFAULT type
        return ParameterType.DEFAULT

    def cleanup(self) -> None:
        """Idempotent cleanup of blend mode state (call on pedalboard unload or re-prepare)."""
        if self.input_controller is None:
            return

        logging.info("Cleaning up blend mode...")

        # Clear any pending parameter updates to prevent stale messages
        if self.handler.ws_bridge:
            cleared = self.handler.ws_bridge.clear_queue()
            if cleared > 0:
                logging.info(f"Cleared {cleared} pending websocket messages")

        # Detach from input and reset tracking
        self.input_controller.detach_from_input()
        self.input_controller.reset_tracking()  # Reset segment cache
        self.input_controller = None

        # Clean up parameter setter and reset MIDI tracking
        if self.parameter_setter:
            self.parameter_setter.reset_tracking()  # Clear MIDI de-dupe tracking
            self.parameter_setter.cleanup()
            self.parameter_setter = None

        # Reset state
        self.stops = []
        self.segment_diff_maps = []
        logging.info("Blend mode cleaned up")

    def check_for_snapshot_changes(self) -> None:
        """
        Check if snapshots.json has been modified and re-prepare if needed.

        This detects when stop snapshots are edited in MOD-UI, allowing
        blend mode to pick up the new parameter values without requiring
        a full pedalboard reload. Note that this file is only modified when
        the pedalboard itself is saved in MOD-UI.

        Called periodically from handler's poll_modui_changes() on the active blend mode only.
        """
        if not self.snapshots_monitor or not self.snapshots_monitor.check_for_change():
            return

        logging.info("Snapshots file modified, re-preparing blend mode with updated stop data...")

        was_active = self.input_controller and self.input_controller.controlled_input is not None
        if was_active:
            self.deactivate()

        # NOTE: We do NOT call sync_blend_snapshots() here to avoid race condition with MOD-UI writes
        # The blend snapshot entries already exist (created during pedalboard load)
        self.cleanup()
        self.prepare()

        if was_active:
            self.activate()

        logging.info("Blend mode re-prepared successfully")
