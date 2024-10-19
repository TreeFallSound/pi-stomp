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
import time
import gpiozero as GPIO
import sys
from rtmidi.midiconstants import CONTROL_CHANGE

import common.token as Token
import pistomp.controller as controller
import pistomp.analogswitch as analogswitch
import pistomp.gpioswitch as gpioswitch
import pistomp.switchstate as switchstate
import common.util as util

class LongpressInfo:
    def __init__(self):
        self.number_in_group = 0
        self.timestamps = dict()

class Footswitch(controller.Controller):
    # Global static info
    all_longpress_groups = {}
    callbacks = {}

    @classmethod
    def init(cls, callbacks):
        # Static dict of dict which stores the timestamps for all footswitch objects
        # The group name serves dual purpose for linking two footswithes and as a key for looking up the callback
        # So each entry should have a corresponding entry in the handler callbacks dict
        # Only these can be used as callbacks.  Any other specified by the user will result in no action.
        cls.all_longpress_groups = {"next_snapshot":LongpressInfo(),
                                    "previous_snapshot":LongpressInfo(),
                                    "toggle_bypass":LongpressInfo(),
                                    "set_mod_tap_tempo":LongpressInfo(),
                                    "toggle_tap_tempo_enable":LongpressInfo()}

        # Static list of possible callbacks from the handler
        if len(cls.callbacks) == 0:
            cls.callbacks = callbacks

    @classmethod
    def check_longpress_events(cls):
        # This should get called once per polling cycle.
        for (group, info) in cls.all_longpress_groups.items():
            num_ts = len(info.timestamps)
            # check for group longpress events (two timestamps, same group within a window were logged)
            if num_ts > 1:
                last = info.timestamps.popitem()[1]
                first = info.timestamps.popitem()[1]
                if abs(last - first) < 0.4:  # Threshold for longpress events to be considered "simultaneous"
                    callback = util.DICT_GET(cls.callbacks, group)
                    if callback:
                        logging.debug("Calling %s" % group)
                        cls._clear_all_groups()
                        callback()
            # check single longpress events (just one timestamp currently logged and the group requires only one fs)
            elif num_ts == 1 and info.number_in_group == 1:
                now = time.monotonic()
                v = list(info.timestamps.values())[0]
                if now >= v + 0.4:
                     # by this time, a second footswitch from a group member has expired, consider it a single
                     callback = util.DICT_GET(cls.callbacks, group)
                     if callback:
                         logging.debug("Calling %s" % group)
                         callback()
                     cls._clear_all_groups()

    @classmethod
    def _clear_all_groups(cls):
        for (g, info) in cls.all_longpress_groups.items():
            info.timestamps.clear()

    def __init__(self, id, led_pin, pixel, midi_CC, midi_channel, midiout, refresh_callback,
                 gpio_input=None, adc_input=None, spi=None, taptempo=None):
        super(Footswitch, self).__init__(midi_channel, midi_CC)
        self.id = id
        self.display_label = None
        self.enabled = False
        self.led = None
        self.midiout = midiout
        self.refresh_callback = refresh_callback
        self.relay_list = []
        self.preset_callback = None
        self.preset_callback_arg = None
        self.lcd_color = None
        self.category = None
        self.pixel = pixel
        self.longpress_groups = []
        self.taptempo = taptempo

        if adc_input and gpio_input:
            logging.error("Switch cannot be specified with both %s and %s", (Token.ADC_INPUT, Token.GPIO_INPUT))
            sys.exit()

        self.gpio_switch = None
        if gpio_input is not None:
            self.gpio_switch = gpioswitch.GpioSwitch(gpio_input, midi_channel, midi_CC, self.pressed,
                                                     taptempo = self.taptempo)

        self.adc_switch = None
        if adc_input is not None:
            self.adc_switch = analogswitch.AnalogSwitch(spi, adc_input, 800, self.pressed, taptempo = self.taptempo)

        if led_pin is not None:
            self.led = GPIO.LED(led_pin)

    def get_display_label(self):
        if self.taptempo and self.taptempo.is_enabled():
            return str(round(self.taptempo.get_bpm()))
        elif self.midi_CC is None:
            return "BPM"
        else:
            return self.display_label

    # Should this be in Controller ?
    def set_midi_CC(self, midi_CC):
        self.midi_CC = midi_CC

    # Should this be in Controller ?
    def set_midi_channel(self, midi_channel):
        self.midi_channel = midi_channel

    def set_value(self, value):
        self.enabled = (value < 1)
        self._set_led(self.enabled)
        self.refresh_callback(footswitch=self)

    def _set_led(self, enabled):
        if self.led is not None:
            if self.taptempo:
                tempo = self.taptempo.get_tap_bpm()
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
            self.pixel.set_color_by_category(category, self.enabled)

    def set_lcd_color(self, color):
        self.lcd_color = color

    def set_longpress_groups(self, groups):
        if isinstance(groups, str):
            groups = groups.split()
        if isinstance(groups, list):
            self.longpress_groups = groups
            for g in groups:
                info = util.DICT_GET(self.all_longpress_groups, g)
                if info is not None:
                    info.number_in_group += 1

    def poll(self):
        if self.adc_switch:
            self.adc_switch.refresh()
        elif self.gpio_switch:
            self.gpio_switch.poll()

    def _log_longpress_events(self):
        # for each group this footswitch is assigned to, keep track of longpress timestamps per group.
        if len(self.longpress_groups) == 0:
            return
        now = time.monotonic()
        for group in self.longpress_groups:
            info = util.DICT_GET(self.all_longpress_groups, group)
            if info is None:
                continue
            logging.debug("longpress event logged")
            info.timestamps.update({self.id: now})

    def pressed(self, state):
        # If a footswitch can be mapped to control a relay, preset, MIDI or all 3
        #
        # The footswitch will only "toggle" if it's associated with a relay
        # (in which case it will toggle with the relay) or with a Midi message
        #
        new_enabled = not self.enabled

        # First handle Longpress Events
        if state is switchstate.Value.LONGPRESSED:
            # Update Relay (if relay is associated with this footswitch)
            if len(self.relay_list) > 0:
                # Pin kept low (long press)
                # toggle the relay and LED, exit this method
                self.enabled = new_enabled
                for r in self.relay_list:
                    if self.enabled:
                        r.enable()
                    else:
                        r.disable()
                self._set_led(self.enabled)
                self.refresh_callback(True)  # True means this is a bypass change only
            else:
                # TODO consider case where relay and longpress are specified
                self._log_longpress_events()
            return

        # Now short Press Events

        if self.taptempo and self.taptempo.is_enabled():
            pass  # Don't process other events when in taptempo mode

        # If mapped to preset change
        elif self.preset_callback is not None:
            # Change the preset and exit this method. Don't flip "enabled" since
            # there is no "toggle" action associated with a preset
            if self.preset_callback_arg is None:
                self.preset_callback()
            else:
                self.preset_callback(self.preset_callback_arg)
            return

        # Send midi
        elif self.midi_CC is not None:
            self.enabled = new_enabled
            # Update LED
            self._set_led(self.enabled)
            cc = [self.midi_channel | CONTROL_CHANGE, self.midi_CC, 127 if self.enabled else 0]
            logging.debug("Sending CC event: %d" % self.midi_CC)
            self.midiout.send_message(cc)

        # Update plugin parameter if any
        if self.parameter is not None:
            self.parameter.value = not self.enabled  # TODO assumes mapped parameter is :bypass

        # Update LCD
        self.refresh_callback(footswitch=self)

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
        self.enabled = False
        self.display_label = None
        self.set_category(None)
        self.preset_callback = None
        self.clear_relays()
