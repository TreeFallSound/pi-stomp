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

from rtmidi import MidiOut
from rtmidi.midiconstants import CONTROL_CHANGE
from typing import Optional, List, Callable
import bisect

import common.util as util
import pistomp.controller as controller
import pistomp.encoder as encoder
from pistomp.handler import Handler
from common.parameter import Parameter, Type

import logging


def clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))

class EncoderController(encoder.Encoder, controller.Controller):
    """
    Encoder with speed-based amplification and parameter quantization.
    If not bound to a Parameter, acts in the standard MIDI range (0-127).
    Currently used for v3 hardware only.
    """

    # Speed thresholds (accumulated rotations between poll cycles)
    FAST_THRESHOLD = 4  # 4+ rotations = very fast
    MEDIUM_THRESHOLD = 2  # 2-3 rotations = fast

    # Multipliers
    FAST_MULTIPLIER = 8
    MEDIUM_MULTIPLIER = 4
    SLOW_MULTIPLIER = 1

    def __init__(
        self,
        handler: Handler,
        d_pin: int,
        clk_pin: int,
        midi_CC: Optional[int],
        midi_channel: int,
        midiout: MidiOut,
        type: Optional[str] = None,
        id: Optional[int] = None,
    ):
        super(EncoderController, self).__init__(
            d_pin=d_pin,
            clk_pin=clk_pin,
            callback=self.refresh,
            type=type,
            id=id,
            midi_CC=midi_CC,
            midi_channel=midi_channel,
        )
        self.handler: Handler = handler
        self.midiout: MidiOut = midiout
        self.value_change_callback: Optional[Callable[[float, "EncoderController"], None]] = None
        self.parameter: Optional[Parameter] = None
        self.step_values: List[float] = []
        self.current_step: int = 0

        # Initialize default quantization (MIDI CC 0-127)
        self._recalculate_steps()
        self.set_value(64)

        logging.debug(f"EncoderController init: id={id}, midi_CC={midi_CC}, midi_channel={midi_channel}")

    @property
    def taper(self) -> float:
        return self.parameter.get_taper() if self.parameter is not None else 1.0

    @property
    def min_val(self) -> float:
        return self.parameter.minimum if self.parameter is not None else self.midi_min

    @property
    def max_val(self) -> float:
        return self.parameter.maximum if self.parameter is not None else self.midi_max

    def _calculate_parameter_resolution(self) -> int:
        """Get the number of discrete steps for the bound parameter."""
        if self.midi_CC is not None or self.parameter is None:
            return 128  # MIDI CC resolution; just a guess for unbound

        if self.parameter.type == Type.INTEGER:
            return int(self.parameter.maximum - self.parameter.minimum) + 1

        if self.parameter.type == Type.ENUMERATION:
            return len(self.parameter.get_enum_value_list())

        if self.parameter.type == Type.TOGGLED:
            return 2

        # Finer resolution for continuous parameters
        return 256

    def _recalculate_steps(self) -> None:
        """Compute step resolution and values based on current range and taper."""
        self.step_values = []

        self.num_steps = self._calculate_parameter_resolution()
        if self.num_steps <= 1:
            self.step_values = [self.min_val]
            return

        _taper = self.taper
        rng = self.max_val - self.min_val
        for i in range(self.num_steps):
            pos = i / (self.num_steps - 1)
            tapered_pos = pos**_taper
            val = self.min_val + (rng * tapered_pos)
            self.step_values.append(val)

    def bind_to_parameter(self, parameter: Parameter) -> None:
        """Initialize quantizer and sync to parameter's current value."""
        self.parameter = parameter
        self._recalculate_steps()
        self.set_value(parameter.value)

        logging.debug(
            f"EncoderController bound to parameter {parameter.name}: "
            f"midi_CC={self.midi_CC}, num_steps={self.num_steps}, value={parameter.value}"
        )

    def set_value(self, value: float) -> None:
        """Update quantizer position to nearest step for the given value."""
        idx = bisect.bisect_left(self.step_values, value)
        if idx == 0:
            self.current_step = 0
        elif idx == len(self.step_values):
            self.current_step = len(self.step_values) - 1
        else:
            if abs(self.step_values[idx - 1] - value) <= abs(self.step_values[idx] - value):
                self.current_step = idx - 1
            else:
                self.current_step = idx

        self.midi_value = self._value_to_midi(self.step_values[self.current_step])

    def _move_steps(self, delta_steps: int) -> float:
        """Move by N steps and return the new parameter value."""
        self.current_step = clamp(self.current_step + delta_steps, 0, len(self.step_values) - 1)
        return self.step_values[self.current_step]

    def refresh(self, rotations: int) -> None:
        """Handle encoder rotation with speed-based amplification."""
        # logging.debug(f"EncoderController.refresh: id={self.id}, type={self.type}, direction={direction}, has_param={self.parameter is not None}")

        # Use accumulated count as speed indicator (accumulated in 10ms poll cycle)
        abs_dir = abs(rotations)
        if abs_dir >= self.FAST_THRESHOLD:
            multiplier = self.FAST_MULTIPLIER
        elif abs_dir >= self.MEDIUM_THRESHOLD:
            multiplier = self.MEDIUM_MULTIPLIER
        else:
            multiplier = self.SLOW_MULTIPLIER

        delta = rotations * multiplier
        new_value = self._move_steps(delta)
        self.midi_value = self._value_to_midi(new_value)
        if self.parameter:
            self.parameter.value = new_value

        # logging.debug(f"Encoder refresh: steps={delta}, value={new_value}, midi={self.midi_value}")

        if self.midi_CC:
            self.midiout.send_message([self.midi_channel | CONTROL_CHANGE, self.midi_CC, int(self.midi_value)])

        if self.value_change_callback:
            self.value_change_callback(new_value, self)
        elif self.parameter:
            self.handler.encoder_value_changed(self.parameter, new_value, self.get_routing_info())
        else:
            # not bound to anything
            pass

    def _value_to_midi(self, value: float) -> int:
        """Convert parameter value to MIDI CC value [0-127]."""
        if self.parameter is None:
            midi_value = value
        else:
            midi_value = util.renormalize(
                value, self.parameter.minimum, self.parameter.maximum, self.midi_min, self.midi_max
            )

        return int(clamp(midi_value, 0, 127))

    def get_normalized_value(self) -> float:
        if self.num_steps <= 1:
            return 0.0
        return self.current_step / (self.num_steps - 1)

    def get_display_info(self) -> controller.AnalogDisplayInfo:
        """Get display information for LCD (analog-controls pattern)."""
        return {
            **super(EncoderController, self).get_display_info(),
            "type": self.type,
            "id": self.id,
            "category": None,  # Set during parameter binding
        }
