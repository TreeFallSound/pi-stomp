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

import logging
from bisect import bisect_right

import common.token as Token
from blend.easing import EasingFunc
from blend.parameter_setter import ParameterSetter
from blend.stop import BlendStop
from blend.types import BlendInputProtocol, EnrichedDiffMap
from pistomp.encoder_controller import EncoderController
from pistomp.input.event import AnalogEvent, ControllerEvent, EncoderEvent

# Detents for a full sweep of an encoder-driven blend; matches the 128-value
# CC grid a bound encoder would otherwise use.
_ENCODER_FULL_SWEEP_DETENTS = 127.0
# Blend's own feel ceiling — independent of the uncapped encoder multiplier
# and of the per-parameter cap in ParameterSteps. Blend has no Parameter /
# ParameterSteps grid (it integrates into its own 0-1 sweep position), so this
# is a local feel decision, not a parameter-resolution one.
_BLEND_MAX_MULTIPLIER = 4.0


class InputController:
    """Receives events from the blend input and interpolates parameters."""

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
        # An encoder reports deltas with no absolute, so blend integrates them
        # into its own sweep position. A pot is read live and ignores this.
        # TODO: blend snapshots mapped to rotary encoders lose position when
        # changing modes — consider a default_value in the blend mode config.
        self.position: float = 0.0

    def attach_to_input(self, control: BlendInputProtocol) -> None:
        """Store reference to the blend input controller."""
        if getattr(control, "type", None) == Token.VOLUME:
            raise ValueError(f"Input {control.id} is a VOLUME controller and cannot be used for blend mode")
        self.controlled_input = control
        logging.info(f"Attached blend mode to {type(control).__name__} {control.id}")

    def detach_from_input(self) -> None:
        if self.controlled_input:
            input_type = type(self.controlled_input).__name__
            input_id = getattr(self.controlled_input, "id", "?")
            logging.info(f"Detaching blend mode from {input_type} (id={input_id})")
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

    def handle_event(self, event: ControllerEvent) -> bool:
        """Interpolate at the input's new position; return True if consumed."""
        if event.controller is not self.controlled_input:
            return False
        match event:
            case EncoderEvent():
                self._advance_sweep(event.rotations * min(event.multiplier, _BLEND_MAX_MULTIPLIER))
            case AnalogEvent():
                pass  # pot carries its own absolute position; read live below
            case _:
                return False
        return self._interpolate()

    # ----------------------------------------------------------------- helpers

    def _advance_sweep(self, detents: float) -> None:
        """Integrate an encoder delta into blend's own sweep position (0-1)."""
        self.position = max(0.0, min(1.0, self.position + detents / _ENCODER_FULL_SWEEP_DETENTS))

    def _interpolate(self) -> bool:
        """Send the diff map for the current position. Guarded — a raised
        exception must never crash the 10ms poll loop."""
        if self.controlled_input is None:
            return False
        try:
            _, _, segment_idx, local_pct = self._resolve_position(self.controlled_input)
            self._send_diff_map(self.segment_diff_maps[segment_idx], local_pct)
            return True
        except Exception as e:
            logging.error(f"Error in blend interpolation: {e}", exc_info=True)
            return False

    def normalized_position(self) -> float:
        """0-1 sweep position of the attached input, for the LCD bar/label."""
        if self.controlled_input is None:
            return 0.0
        return self._position_for(self.controlled_input)

    def _position_for(self, control: BlendInputProtocol) -> float:
        # An encoder has no absolute reading — blend's integrated position is
        # authoritative. A pot reports its own absolute, read live.
        if isinstance(control, EncoderController):
            return self.position
        return control.get_normalized_value()

    def _resolve_position(self, control: BlendInputProtocol) -> tuple[float, float, int, float]:
        """Return (t, x, segment_idx, local_pct) for the control's current position."""
        t = self._position_for(control)
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
