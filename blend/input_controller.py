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

from blend.easing import EasingFunc
from blend.stop import BlendStop
from blend.types import BlendInputProtocol, EnrichedDiffMap
from blend.parameter_setter import ParameterSetter


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
        """
        Attach blend mode callback to analog input (expression pedal or encoder).

        Hijacks the value_change_callback to intercept value changes and route
        them through the interpolation system.
        """
        # Search analog_controls first (expression pedals)
        for control in analog_controls:
            if hasattr(control, "id") and control.id == input_id:
                self.controlled_input = control
                control.value_change_callback = self.handle_value_change
                logging.info(f"Attached blend mode to analog control {input_id}")
                return

        # Search encoders (tweak encoders)
        for encoder in encoders:
            if hasattr(encoder, "id") and encoder.id == input_id:
                from pistomp.encodermidicontrol import EncoderMidiControl

                if not isinstance(encoder, EncoderMidiControl):
                    raise ValueError(f"Encoder {input_id} must be EncoderMidiControl (has MIDI support) for blend mode")

                self.controlled_input = encoder
                encoder.value_change_callback = self.handle_value_change
                logging.info(f"Attached blend mode to encoder {input_id}")
                return

        raise ValueError(f"Input {input_id} not found in analog_controls or encoders")

    def detach_from_input(self) -> None:
        """Remove blend mode callback from input."""
        if self.controlled_input:
            input_type = type(self.controlled_input).__name__
            input_id = getattr(self.controlled_input, "id", "?")
            logging.info(f"Detaching blend mode from {input_type} (id={input_id})")
            self.controlled_input.value_change_callback = None
            self.controlled_input = None
        else:
            logging.warning("detach_from_input called but no controlled_input attached")

    def reset_tracking(self) -> None:
        pass

    def _get_normalized_position(self, control: BlendInputProtocol) -> float:
        from pistomp.encodermidicontrol import EncoderMidiControl

        if isinstance(control, EncoderMidiControl):
            # Encoder: MIDI value already accumulated (0-127)
            return control.midi_value / 127.0
        else:
            # Expression pedal: ADC value (0-1023)
            return control.last_read / 1023.0

    def sync_current_position(self) -> None:
        """Recalculate and update the controlled input based on current position."""
        if not self.controlled_input:
            logging.warning("Cannot sync - no controlled input attached")
            return

        # Get normalized position from control and apply easing
        t = self._get_normalized_position(self.controlled_input)
        x = self.easing_func(t)

        # Find segment and local position within it
        segment_idx = self._find_segment(x)
        lower = self.stops[segment_idx]
        upper = self.stops[segment_idx + 1]
        segment_range = upper.position - lower.position

        local_pct = max(0.0, min(1.0, (x - lower.position) / segment_range)) if segment_range > 0 else 0.0

        # Send differing parameters (linearly interpolated within segment)
        diff_map = self.segment_diff_maps[segment_idx]
        diff_sent = 0
        for instance_id, params in diff_map.items():
            for symbol, param_data in params.items():
                float_value = param_data.val_a + (param_data.val_b - param_data.val_a) * local_pct
                if self.parameter_setter.send_parameter(instance_id, symbol, float_value):
                    diff_sent += 1
                else:
                    logging.debug(f"Skipped differing param {instance_id}/{symbol} = {float_value:.3f}")

        # Send non-differing parameters (constant from first stop)
        # These are in first stop but NOT in any diff map
        first_stop_state = self.stops[0].snapshot_state
        const_sent = 0
        for instance_id, params in first_stop_state.items():
            for symbol, value in params.items():
                # Skip if already sent as differing parameter
                if instance_id in diff_map and symbol in diff_map[instance_id]:
                    continue
                # Send constant value
                if self.parameter_setter.send_parameter(instance_id, symbol, value):
                    const_sent += 1
                else:
                    logging.debug(f"Skipped constant param {instance_id}/{symbol} = {value:.3f}")

        logging.info(
            f"Synced blend mode to position t={t:.3f} x={x:.3f} (segment {segment_idx}): sent {diff_sent} differing + {const_sent} constant = {diff_sent + const_sent} total parameters"
        )

    def handle_value_change(self, _raw_value: int, control: BlendInputProtocol) -> None:
        """
        Handle analog input movement (critical performance path).
        Callback from expression pedal or encoder when value changes;
        performs interpolation and sends parameters.
        """
        t = self._get_normalized_position(control)
        x = self.easing_func(t)
        segment_idx = self._find_segment(x)
        diff_map = self.segment_diff_maps[segment_idx]

        lower = self.stops[segment_idx]
        upper = self.stops[segment_idx + 1]
        segment_range = upper.position - lower.position
        local_pct = max(0.0, min(1.0, (x - lower.position) / segment_range)) if segment_range > 0 else 0.0

        try:
            for instance_id, params in diff_map.items():
                for symbol, param_data in params.items():
                    float_value = param_data.val_a + (param_data.val_b - param_data.val_a) * local_pct
                    self.parameter_setter.send_parameter(instance_id, symbol, float_value)
        except Exception as e:
            logging.error(f"Error in blend interpolation: {e}", exc_info=True)
            # Continue operation - don't crash the polling loop

    def _find_segment(self, percentage: float) -> int:
        return max(0, min(bisect_right(self._stop_positions, percentage) - 1, len(self.stops) - 2))
