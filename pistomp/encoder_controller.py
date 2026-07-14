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

from __future__ import annotations

import logging
import time
from typing import List, Optional

import common.util as util
import pistomp.controller as controller
import pistomp.analogswitch as analogswitch
import pistomp.gpioswitch as gpioswitch
import pistomp.switchstate as switchstate
from common.parameter import Parameter
from common.parameter_steps import ParameterSteps, resolution
from pistomp.encoder import Encoder
from pistomp.input.event import EncoderEvent, SwitchEvent, SwitchEventKind


def _clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


class EncoderController(controller.Controller):
    """Rotary encoder Controller. Owns a hardware Encoder, parameter quantizer,
    and optional absorbed button. Dispatches events via self.sink.

    Two modes, distinguished by the handler via controller.type — not by the
    controller itself, which dispatches identically in both:
    - Nav mode (type=Token.NAV): the quantizer still advances, but the handler
      reads only event.rotations and ignores new_value/new_midi_value.
    - Param mode (midi_channel + midi_CC): the handler consumes the quantized
      new_value/new_midi_value.

    In both modes the quantizer is built at construction (whenever type or
    midi_CC is set); nav simply leaves its output unused downstream.

    Button: if sw_pin is provided, owns a GpioSwitch that emits SwitchEvent
    via self.sink. If sw_adc_chan is provided, owns an AnalogSwitch instead.
    Longpress is stored as a string callback name resolved by the handler at
    dispatch time.
    """

    # Speed amplification: at this per-detent interval, multiplier = 1×.
    REFERENCE_DT_MS = 80.0
    MAX_MULTIPLIER = 4.0
    MIN_MULTIPLIER = 1.0

    def __init__(
        self,
        d_pin: int | None,
        clk_pin: int | None,
        *,
        midi_channel: int = 0,
        midi_CC: Optional[int] = None,
        type: Optional[str] = None,
        id: Optional[int] = None,
        sw_pin: Optional[int] = None,
        sw_adc_chan: Optional[int] = None,
        spi: Optional[object] = None,
        longpress: Optional[str] = None,  # string name; resolved by handler at dispatch
        max_drain: int = Encoder.DEFAULT_MAX_DRAIN,
    ):
        controller.Controller.__init__(self, midi_channel, midi_CC)
        self._hw_encoder = Encoder(d_pin, clk_pin, max_drain=max_drain)
        self.type = type
        self.id = id

        # Param-mode quantizer state (inert until bound or used)
        self._recalculate_steps()
        self._last_detent_time: Optional[float] = None
        self._last_direction: int = 0
        if midi_channel is not None and midi_CC is not None or type is not None:
            self.set_value(64)

        # Absorbed button (GPIO or ADC)
        self._button: Optional[gpioswitch.GpioSwitch | analogswitch.AnalogSwitch] = None
        self.longpress: Optional[str] = longpress  # string name; resolved at dispatch
        if sw_pin is not None:
            self._button = gpioswitch.GpioSwitch(
                sw_pin,
                callback=self._on_button,
                longpress_callback=self._on_button_longpress,
            )
        elif sw_adc_chan is not None:
            self._button = analogswitch.AnalogSwitch(
                spi,
                sw_adc_chan,
                callback=self._on_button,
                longpress_callback=self._on_button_longpress,
            )

        logging.debug(
            "EncoderController init: id=%s, midi_CC=%s, sw_pin=%s, sw_adc_chan=%s",
            id,
            midi_CC,
            sw_pin,
            sw_adc_chan,
        )

    # ── Poll ─────────────────────────────────────────────────────────────

    def read_rotary(self) -> None:
        """Called from hardware.poll_controls(). Reads direction from the hardware
        decoder and dispatches via refresh()."""
        d = self._hw_encoder.read_rotary()
        if d != 0:
            self.refresh(d)

    def poll(self) -> None:
        """Called from hardware.poll_controls(). Polls the absorbed button."""
        if self._button is not None:
            if isinstance(self._button, gpioswitch.GpioSwitch):
                self._button.poll()
            else:
                self._button.refresh()

    # ── Quantizer ────────────────────────────────────────────────────────

    @property
    def taper(self) -> float:
        return self.parameter.get_taper() if self.parameter is not None else 1.0

    @property
    def min_val(self) -> float:
        return self.parameter.minimum if self.parameter is not None else self.midi_min

    @property
    def max_val(self) -> float:
        return self.parameter.maximum if self.parameter is not None else self.midi_max

    @property
    def step_values(self) -> List[float]:
        return self._steps.values

    @property
    def num_steps(self) -> int:
        return self._steps.num_steps

    @property
    def current_step(self) -> int:
        return self._steps.index

    @current_step.setter
    def current_step(self, index: int) -> None:
        self._steps.index = _clamp(index, 0, len(self._steps.values) - 1)

    def _recalculate_steps(self) -> None:
        self._steps = ParameterSteps(self.min_val, self.max_val, self.taper, resolution(self.parameter))

    def bind_to_parameter(self, parameter: Parameter) -> None:
        self.unbind_from_parameter()
        self.parameter = parameter
        self._recalculate_steps()
        self.set_value(parameter.value)
        self._unsub_param = parameter.subscribe(lambda _p: self.set_value(_p.value))
        logging.debug(
            f"EncoderController bound: id={self.id}, param={parameter.name}, "
            f"midi_CC={self.midi_CC}, num_steps={self.num_steps}, value={parameter.value}"
        )

    def set_value(self, value: float) -> None:
        self._steps.set_value(value)
        self.midi_value = self._value_to_midi(self._steps.value)

    def _move_steps(self, delta_steps: int) -> float:
        return self._steps.move(delta_steps)

    def _compute_multiplier(self, rotations: int) -> float:
        now = time.monotonic()
        last = self._last_detent_time
        last_dir = self._last_direction
        direction = 1 if rotations > 0 else -1 if rotations < 0 else 0
        self._last_detent_time = now
        self._last_direction = direction

        if rotations == 0 or last is None or direction != last_dir:
            return self.MIN_MULTIPLIER
        dt = now - last
        if dt <= 0:
            return self.MAX_MULTIPLIER
        dt_per_detent_ms = (dt * 1000.0) / abs(rotations)
        return _clamp(self.REFERENCE_DT_MS / dt_per_detent_ms, self.MIN_MULTIPLIER, self.MAX_MULTIPLIER)

    def _value_to_midi(self, value: float) -> int:
        if self.parameter is None:
            midi_value = value
        else:
            midi_value = util.renormalize(
                value,
                self.parameter.minimum,
                self.parameter.maximum,
                self.midi_min,
                self.midi_max,
            )
        return int(_clamp(midi_value, 0, 127))

    def get_normalized_value(self) -> float:
        if self.num_steps <= 1:
            return 0.0
        return self.current_step / (self.num_steps - 1)

    def get_display_info(self) -> controller.AnalogDisplayInfo:
        info: controller.AnalogDisplayInfo = {"category": None}
        if self.type is not None:
            info["type"] = self.type
        if self.id is not None:
            info["id"] = self.id
        return info

    # ── Dispatch ─────────────────────────────────────────────────────────

    def refresh(self, rotations: int) -> None:
        """Handle a tick's worth of detents."""
        multiplier = self._compute_multiplier(rotations)
        delta = int(round(rotations * multiplier))
        new_value = self._move_steps(delta)
        self.midi_value = self._value_to_midi(new_value)
        if self.parameter is not None:
            self.parameter.value = new_value

        self.sink.handle(
            EncoderEvent(
                controller=self,
                rotations=rotations,
                multiplier=multiplier,
                new_value=new_value,
                new_midi_value=self.midi_value,
            )
        )

    # ── Button ───────────────────────────────────────────────────────────

    def set_longpress(self, name: Optional[str]) -> None:
        """Set the longpress callback name. Called from Hardware.__init_encoders
        on pedalboard load to overlay per-pedalboard config."""
        self.longpress = name

    def _on_button(self, state, timestamp: float) -> None:
        if state == switchstate.Value.LONGPRESSED:
            return
        self.sink.handle(SwitchEvent(controller=self, kind=SwitchEventKind.PRESS, timestamp=timestamp))

    def _on_button_longpress(self, state, timestamp: float) -> None:
        self.sink.handle(SwitchEvent(controller=self, kind=SwitchEventKind.LONGPRESS, timestamp=timestamp))
