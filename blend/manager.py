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

"""BlendMode coordinator: lifecycle, diff-map pre-computation, input wiring."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from blend.easing import EASING_FUNCTIONS, EasingFunc
from blend.input_controller import InputController
from blend.parameter_setter import ParameterSetter
from blend.snapshot import SnapshotManager
from blend.stop import BlendStop, build_segment_diff_map
from blend.types import (
    BlendSnapshotConfig,
    EnrichedDiffMap,
    InstanceId,
    MidiBoundParams,
    NormalizedStops,
    Symbol,
)
from modalapi.parameter import Type as ParameterType
from modalapi.pedalboard_monitor import FileChangeMonitor

if TYPE_CHECKING:
    from modalapi.modhandler import Modhandler


def _normalize_stops_config(
    stops_config: dict[str, int | str] | list[str | int],
) -> NormalizedStops:
    """Convert list-form stops to dict-form with evenly spaced positions."""
    if isinstance(stops_config, dict):
        return stops_config

    if not isinstance(stops_config, list):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError(f"Stops must be dict or list, got {type(stops_config)}")
    if len(stops_config) < 2:
        raise ValueError("Stops list must have at least 2 entries")

    step = 1.0 / (len(stops_config) - 1)
    normalized: NormalizedStops = {f"{i * step:.6f}": snapshot_id for i, snapshot_id in enumerate(stops_config)}
    logging.debug(f"Normalized list stops to: {normalized}")
    return normalized


def _resolve_easing(config: BlendSnapshotConfig) -> EasingFunc:
    name = config.get("interpolation", "linear")
    easing = EASING_FUNCTIONS.get(name)
    if not easing:
        raise ValueError(f"Invalid interpolation '{name}', must be one of: {', '.join(EASING_FUNCTIONS.keys())}")
    return easing


class BlendMode:
    """Coordinates blend mode components to enable smooth parameter interpolation."""

    def __init__(self, handler: Any, config: BlendSnapshotConfig) -> None:
        self.handler: Modhandler = handler
        self.config: BlendSnapshotConfig = config
        self.stops: list[BlendStop] = []
        self.segment_diff_maps: list[EnrichedDiffMap] = []
        self.parameter_setter: ParameterSetter | None = None
        self.input_controller: InputController | None = None
        self.snapshots_monitor: FileChangeMonitor | None = None

    # ---------------------------------------------------------------- lifecycle

    def prepare(self) -> None:
        """Pre-compute segment diff maps so the hot path stays a dict iteration + lerp."""
        logging.info("Preparing blend mode...")

        easing = _resolve_easing(self.config)
        self.stops = self._create_stops()
        midi_bound = self._extract_midi_bound_parameters()

        self.segment_diff_maps = []
        for i in range(len(self.stops) - 1):
            lower, upper = self.stops[i], self.stops[i + 1]
            diff_map = build_segment_diff_map(lower, upper, self._get_parameter_type, midi_bound)
            self.segment_diff_maps.append(diff_map)
            count = sum(len(p) for p in diff_map.values())
            logging.debug(f"  Segment {i} ({lower.position:.2f} -> {upper.position:.2f}): {count} differing parameters")

        if self.config.get("input_id") is None:
            raise ValueError("Blend mode requires 'input_id' config")

        if self.handler.ws_bridge is None:
            raise RuntimeError("Blend mode requires an active WebSocket bridge")
        assert self.handler.current is not None, "Blend mode requires a loaded pedalboard"

        self.parameter_setter = ParameterSetter(self.handler.ws_bridge)
        self.input_controller = InputController(easing, self.stops, self.segment_diff_maps, self.parameter_setter)
        snapshots_path = Path(self.handler.current.pedalboard.bundle) / "snapshots.json"
        self.snapshots_monitor = FileChangeMonitor(str(snapshots_path))
        logging.info(f"Blend mode prepared with {len(self.stops)} stops")

    def activate(self) -> None:
        """Attach to input and push current position so all params are set."""
        if not self.input_controller or not self.parameter_setter:
            raise RuntimeError("Cannot activate - blend mode not prepared")

        input_id = self.config["input_id"]
        self.parameter_setter.reset_tracking()
        self.input_controller.attach_to_input(
            self.handler.hardware.analog_controls, self.handler.hardware.encoders, input_id
        )

        try:
            self.input_controller.sync_current_position()
        except Exception:
            self.input_controller.detach_from_input()
            raise

        logging.info(f"Activated blend mode: '{self.config.get('name')}'")

    def deactivate(self) -> None:
        """Detach from input. Idempotent."""
        if not self.input_controller:
            return

        self._clear_ws_queue()
        self.input_controller.detach_from_input()
        if self.parameter_setter:
            self.parameter_setter.reset_tracking()
        logging.info(f"Deactivated blend mode: '{self.config.get('name')}'")

    def cleanup(self) -> None:
        """Full teardown (pedalboard unload or re-prepare). Idempotent."""
        if self.input_controller is None:
            return

        logging.info("Cleaning up blend mode...")
        self.deactivate()
        self.input_controller = None
        if self.parameter_setter:
            self.parameter_setter.cleanup()
            self.parameter_setter = None
        self.stops = []
        self.segment_diff_maps = []
        logging.info("Blend mode cleaned up")

    def check_for_snapshot_changes(self) -> None:
        """Re-prepare if snapshots.json was edited in MOD-UI.

        We deliberately do NOT call SnapshotManager.sync_blend_snapshots() here:
          - it would race with MOD-UI's truncate-then-write save path,
          - any write of ours bumps mtime and re-triggers this very check,
          - the blend snapshot wrapper entries already exist (created at pedalboard load),
            so there is nothing to sync — only stop contents to re-read.
        """
        if not self.snapshots_monitor or not self.snapshots_monitor.check_for_change():
            return

        logging.info("Snapshots file modified, re-preparing blend mode with updated stop data...")
        was_active = self.input_controller is not None and self.input_controller.controlled_input is not None
        if was_active:
            self.deactivate()
        self.cleanup()
        self.prepare()
        if was_active:
            self.activate()
        logging.info("Blend mode re-prepared successfully")

    # ----------------------------------------------------------------- helpers

    def _clear_ws_queue(self) -> None:
        if self.handler.ws_bridge:
            cleared = self.handler.ws_bridge.clear_queue()
            if cleared > 0:
                logging.debug(f"Cleared {cleared} pending WebSocket messages")

    def _extract_midi_bound_parameters(self) -> MidiBoundParams:
        """Collect (instance_id, symbol) for every MIDI-bound parameter on the current pedalboard."""
        assert self.handler.current is not None
        midi_params: MidiBoundParams = set()
        for plugin in self.handler.current.pedalboard.plugins:
            for symbol, param in plugin.parameters.items():
                if param.binding is not None:
                    midi_params.add((plugin.instance_id, symbol))
                    logging.debug(f"Found MIDI binding: {plugin.instance_id}/{symbol} -> {param.binding}")
        if midi_params:
            logging.info(f"Excluding {len(midi_params)} MIDI-bound parameters from blend interpolation")
        return midi_params

    def _create_stops(self) -> list[BlendStop]:
        """Resolve config stops → sorted, validated list of BlendStop."""
        stops_config = self.config.get("stops")
        if not stops_config:
            raise ValueError("Blend mode requires 'stops' config")

        snapshot_stops = _normalize_stops_config(stops_config)
        if len(snapshot_stops) < 2:
            raise ValueError(f"Blend mode requires at least 2 stops, got {len(snapshot_stops)}")

        assert self.handler.current is not None, "Blend mode requires a loaded pedalboard"
        bundle_path = Path(self.handler.current.pedalboard.bundle)
        snapshots_data = SnapshotManager.read_snapshots_file(bundle_path)

        stops: list[BlendStop] = []
        for position_str, snapshot_identifier in snapshot_stops.items():
            try:
                position = float(position_str)
            except ValueError:
                raise ValueError(
                    f"Invalid position key '{position_str}': must be a stringified float (e.g., '0.0', '0.5')"
                )
            if not 0.0 <= position <= 1.0:
                raise ValueError(f"Position {position} out of range: must be between 0.0 and 1.0")

            snapshot_index = SnapshotManager.resolve_snapshot_identifier(snapshots_data, snapshot_identifier)
            state = SnapshotManager.parse_snapshot_data(snapshots_data, snapshot_index)
            stops.append(BlendStop(position, snapshot_index, state))

        stops.sort(key=lambda s: s.position)

        # Hermite/Catmull-Rom would need 2 stops of context on each side, so we cap at 4.
        if len(stops) > 4:
            logging.warning(f"Limiting to 4 stops (got {len(stops)})")
            stops = stops[:4]

        for i in range(len(stops) - 1):
            pos_a, pos_b = stops[i].position, stops[i + 1].position
            if pos_a >= pos_b:
                raise ValueError(
                    f"Stop positions must be strictly increasing: stop {i} at {pos_a}, stop {i + 1} at {pos_b}"
                )
            if int(pos_a * 127) == int(pos_b * 127):
                raise ValueError(
                    f"Stop positions too close - both map to CC {int(pos_a * 127)}: "
                    f"stop {i} at {pos_a}, stop {i + 1} at {pos_b}. Minimum separation is {1.0 / 127:.6f}"
                )

        for stop in stops:
            logging.debug(f"Created {stop}")
        return stops

    def _get_parameter_type(self, instance_id: InstanceId, symbol: Symbol) -> ParameterType:
        assert self.handler.current is not None
        for plugin in self.handler.current.pedalboard.plugins:
            if plugin.instance_id == instance_id:
                param = plugin.parameters.get(symbol)
                if param:
                    return param.type
        return ParameterType.DEFAULT
