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

"""Analog input hijacking and control for blend mode."""

import logging
from bisect import bisect_right

import common.token as Token
from blend.easing import EasingFunc
from blend.parameter_setter import ParameterSetter
from blend.stop import BlendStop
from blend.types import BlendInputProtocol, EnrichedDiffMap


class InputController:
    """Hijacks analog input callbacks to implement blend mode interpolation."""

    def __init__(
        self,
        easing_func: EasingFunc,
        stops: list[BlendStop],
        segment_diff_maps: list[EnrichedDiffMap],
        parameter_setter: ParameterSetter,
    ) -> None:
        self.easing_func = easing_func
        self.stops = stops
        self.segment_diff_maps = segment_diff_maps
        self.parameter_setter = parameter_setter
        self.controlled_input: BlendInputProtocol | None = None
        self._stop_positions = [s.position for s in stops]

    def attach_to_input(self, analog_controls: list, encoders: list, input_id: int) -> None:
        """Hijack `value_change_callback` on the input matching `input_id`."""
        for control in (*analog_controls, *encoders):
            if getattr(control, "id", None) != input_id:
                continue
            if getattr(control, "type", None) == Token.VOLUME:
                raise ValueError(f"Input {input_id} is a VOLUME controller and cannot be used for blend mode")
            if not hasattr(control, "get_normalized_value"):
                raise ValueError(f"Input {input_id} does not support blend mode (missing get_normalized_value)")
            self.controlled_input = control
            control.value_change_callback = self.handle_value_change
            logging.info(f"Attached blend mode to {type(control).__name__} {input_id}")
            return

        raise ValueError(f"Input {input_id} not found in analog_controls or encoders")

    def detach_from_input(self) -> None:
        if self.controlled_input:
            input_type = type(self.controlled_input).__name__
            input_id = getattr(self.controlled_input, "id", "?")
            logging.info(f"Detaching blend mode from {input_type} (id={input_id})")
            self.controlled_input.value_change_callback = None
            self.controlled_input = None
        else:
            logging.warning("detach_from_input called but no controlled_input attached")

    def sync_current_position(self) -> None:
        """Push diff-map params at current input position, plus first-stop constants."""
        if not self.controlled_input:
            logging.warning("Cannot sync - no controlled input attached")
            return

        t, x, segment_idx, local_pct = self._resolve_position(self.controlled_input)
        diff_map = self.segment_diff_maps[segment_idx]

        diff_sent = self._send_diff_map(diff_map, local_pct, log_skips=True)

        const_sent = 0
        for instance_id, params in self.stops[0].snapshot_state.items():
            for symbol, value in params.items():
                if instance_id in diff_map and symbol in diff_map[instance_id]:
                    continue
                if self.parameter_setter.send_parameter(instance_id, symbol, value):
                    const_sent += 1
                else:
                    logging.debug(f"Skipped constant param {instance_id}/{symbol} = {value:.3f}")

        logging.info(
            f"Synced blend mode to position t={t:.3f} x={x:.3f} (segment {segment_idx}): "
            f"sent {diff_sent} differing + {const_sent} constant = {diff_sent + const_sent} total parameters"
        )

    def handle_value_change(self, _raw: int, control: BlendInputProtocol) -> None:
        """Critical-path callback from expression pedal or encoder."""
        try:
            _, _, segment_idx, local_pct = self._resolve_position(control)
            self._send_diff_map(self.segment_diff_maps[segment_idx], local_pct)
        except Exception as e:
            # Don't crash the polling loop.
            logging.error(f"Error in blend interpolation: {e}", exc_info=True)

    # ----------------------------------------------------------------- helpers

    def _resolve_position(self, control: BlendInputProtocol) -> tuple[float, float, int, float]:
        """Return (t, x, segment_idx, local_pct) for the control's current position."""
        t = control.get_normalized_value()
        x = self.easing_func(t)
        segment_idx = self._find_segment(x)
        lower = self.stops[segment_idx].position
        upper = self.stops[segment_idx + 1].position
        span = upper - lower
        local_pct = max(0.0, min(1.0, (x - lower) / span)) if span > 0 else 0.0
        return t, x, segment_idx, local_pct

    def _send_diff_map(self, diff_map: EnrichedDiffMap, local_pct: float, log_skips: bool = False) -> int:
        sent = 0
        for instance_id, params in diff_map.items():
            for symbol, p in params.items():
                value = p.val_a + (p.val_b - p.val_a) * local_pct
                if self.parameter_setter.send_parameter(instance_id, symbol, value):
                    sent += 1
                elif log_skips:
                    logging.debug(f"Skipped differing param {instance_id}/{symbol} = {value:.3f}")
        return sent

    def _find_segment(self, percentage: float) -> int:
        return max(0, min(bisect_right(self._stop_positions, percentage) - 1, len(self.stops) - 2))
