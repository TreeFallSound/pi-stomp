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
import sys
from typing_extensions import override

import common.token as Token
import pistomp.controller as controller
import pistomp.analogswitch as analogswitch
import pistomp.gpioswitch as gpioswitch
import pistomp.switchstate as switchstate
from pistomp.input.event import SwitchEvent, SwitchEventKind


class Footswitch(controller.Controller):

    def __init__(self, id, led_pin, pixel, midi_CC, midi_channel, refresh_callback,
                 gpio_input=None, adc_input=None, spi=None, taptempo=None):
        super(Footswitch, self).__init__(midi_channel, midi_CC)
        self.id: int = id
        self.display_label = None
        self.toggled = False
        self.led = None
        self.refresh_callback = refresh_callback
        self.relay_list = []
        self.preset_callback = None
        self.preset_callback_arg = None
        self.lcd_color = None
        self.category = None
        self.pixel = pixel
        self.longpress_groups = []
        self.disabled = False
        self.taptempo = taptempo

        if adc_input and gpio_input:
            logging.error("Switch cannot be specified with both %s and %s", (Token.ADC_INPUT, Token.GPIO_INPUT))
            sys.exit()

        self.gpio_switch = None
        if gpio_input is not None:
            self.gpio_switch = gpioswitch.GpioSwitch(gpio_input, self._on_switch,
                                                     longpress_callback=self._on_switch)

        self.adc_switch = None
        if adc_input is not None:
            self.adc_switch = analogswitch.AnalogSwitch(spi, adc_input, self._on_switch,
                                                         longpress_callback=self._on_switch)

        if led_pin is not None:
            try:
                import gpiozero as GPIO  # pyright: ignore[reportMissingImports]
                self.led = GPIO.LED(led_pin)
            except Exception as e:
                logging.error("Initializing LED for footswitch %d: %s" % (id, str(e)))

    def get_display_label(self):
        if self.taptempo and self.taptempo.is_enabled():
            return str(round(self.taptempo.get_bpm()))
        elif self.midi_CC is None:
            return ""
        else:
            return self.display_label

    # Should this be in Controller ?
    def set_midi_CC(self, midi_CC):
        self.midi_CC = midi_CC

    # Should this be in Controller ?
    def set_midi_channel(self, midi_channel):
        self.midi_channel = midi_channel

    @property
    def drives_display(self) -> bool:
        """True when unbound: no inbound echo will arrive, so the press updates
        indicators itself. When bound to a plugin :bypass, the WS broadcast does."""
        return self.parameter is None

    @override
    def set_value(self, value: float):
        self.toggled = (value < 1)
        self.set_led(self.toggled)
        self.refresh_callback(footswitch=self)

    def current_toggle_state(self) -> bool:
        return self.toggled

    def toggle_relays(self, enabled: bool):
        for r in self.relay_list:
            if enabled:
                r.enable()
            else:
                r.disable()

    def set_led(self, enabled):
        if self.led is not None:
            if self.taptempo:
                tempo = self.taptempo.get_bpm()
                if tempo:
                    period = 60/tempo
                    on = 0.1
                    self.led.blink(on_time=on, off_time=period - 0.1)
            elif enabled:
                self.led.on()
            else:
                self.led.off()
        if self.pixel:
            self.pixel.set_enable(enabled)

    def set_category(self, category):
        self.category = category
        if self.pixel:
            self.pixel.set_color_by_category(category, self.toggled)

    def set_lcd_color(self, color):
        self.lcd_color = color

    def set_longpress_groups(self, groups):
        if groups is None:
            self.longpress_groups = []
        elif isinstance(groups, str):
            self.longpress_groups = groups.split()
        elif isinstance(groups, list):
            self.longpress_groups = groups

    def poll(self):
        if self.disabled:
            return
        if self.adc_switch:
            self.adc_switch.refresh()
        elif self.gpio_switch:
            self.gpio_switch.poll()

    def _on_switch(self, state, timestamp=0.0):
        # Pure dispatch: map hardware state to a SwitchEvent and hand it to the
        # sink. All toggle / relay / MIDI / preset logic lives in the handler.
        if self.disabled:
            return
        kind = (SwitchEventKind.LONGPRESS if state is switchstate.Value.LONGPRESSED
                else SwitchEventKind.PRESS)
        self.sink.handle(SwitchEvent(controller=self, kind=kind, timestamp=timestamp))

    def set_display_label(self, label):
        self.display_label = label

    def add_relay(self, relay):
        self.relay_list.append(relay)
        self.set_value(not relay.init_state())

    def clear_relays(self):
        self.relay_list.clear()

    def add_preset(self, callback, callback_arg=None):
        self.preset_callback = callback
        self.preset_callback_arg = callback_arg

    def clear_pedalboard_info(self):
        self.toggled = False
        self.disabled = False
        self.display_label = None
        self.set_category(None)
        self.preset_callback = None
        self.clear_relays()
