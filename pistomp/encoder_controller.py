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
from typing import Optional

import common.util as util
import pistomp.controller as controller
import pistomp.analogswitch as analogswitch
import pistomp.gpioswitch as gpioswitch
import pistomp.switchstate as switchstate
from pistomp.encoder import Encoder
from pistomp.input.event import EncoderEvent, SwitchEvent, SwitchEventKind


def _clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


# Unbound fallback CC seeds at midpoint so a fresh tweak reads 50%.
ENCODER_FALLBACK_DEFAULT = 64


def encoder_key(controller: "EncoderController") -> str:
    """Handler key for an encoder's unbound fallback CC. Same "channel:CC" shape
    the effective table and external-parameter binding use."""
    return f"{controller.midi_channel}:{controller.midi_CC}"


class EncoderController(controller.Controller):
    """Rotary encoder Controller. Owns a hardware Encoder and an optional
    absorbed button. Dispatches events via self.sink.

    An encoder is a delta source: refresh() reports rotations at a speed
    multiplier and nothing more. It owns no copy of a value that belongs to
    something else — the owner (a parameter via the handler, blend, a menu
    selection) integrates the delta into whatever it owns. An unbound encoder
    still emits a CC so mod-ui can MIDI-learn it (input/README.md), but that
    fallback accumulator belongs to the handler (the emitter), not here.

    Button: if sw_pin is provided, owns a GpioSwitch that emits SwitchEvent
    via self.sink. If sw_adc_chan is provided, owns an AnalogSwitch instead.
    Longpress is stored as a string callback name resolved by the handler at
    dispatch time.
    """

    # Speed amplification: at this per-detent interval, multiplier = 1×.
    REFERENCE_DT_MS = 80.0
    # Raw multiplier ceiling. High because the effective cap lives in
    # ParameterSteps.effective_multiplier (per-parameter, resolution-aware);
    # this only bounds the degenerate dt<=0 case and very fast spins on big
    # grids. Each consumer (blend, fallback CC, params) applies its own cap.
    MAX_MULTIPLIER = 1000.0
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

        self._last_detent_time: Optional[float] = None
        self._last_direction: int = 0

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

    # ── Value ────────────────────────────────────────────────────────────

    def bar_midi_value(self) -> int:
        """0-127 for the LCD bar and the MIDI-learn emit of a *bound* encoder,
        derived from the parameter (the owner). Unbound, the value lives on the
        handler — ask Modhandler.encoder_fallback."""
        assert self.parameter is not None, "bar_midi_value is bound-only; unbound lives on the handler"
        midi_value = util.renormalize(
            self.parameter.value,
            self.parameter.minimum,
            self.parameter.maximum,
            self.midi_min,
            self.midi_max,
        )
        return int(_clamp(midi_value, 0, 127))

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
        self.sink.handle(EncoderEvent(controller=self, rotations=rotations, multiplier=multiplier))

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
