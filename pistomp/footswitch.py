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
import RPi.GPIO as GPIO
from rtmidi.midiconstants import CONTROL_CHANGE

import pistomp.gpioswitch as gpioswitch

class Footswitch(gpioswitch.GpioSwitch):

    def __init__(self, id, fs_pin, led_pin, midi_CC, midi_channel, midiout, refresh_callback):
        super(Footswitch, self).__init__(fs_pin, midi_channel, midi_CC)
        self.id = id
        self.display_label = None
        self.enabled = False
        self.fs_pin = fs_pin
        self.led_pin = led_pin
        self.midiout = midiout
        self.refresh_callback = refresh_callback
        self.relay_list = []
        self.preset_callback = None
        self.lcd_color = None

        if led_pin is not None:
            GPIO.setup(led_pin, GPIO.OUT)
            self._set_led(GPIO.LOW)

    # Should this be in Controller ?
    def set_midi_CC(self, midi_CC):
        self.midi_CC = midi_CC

    # Should this be in Controller ?
    def set_midi_channel(self, midi_channel):
        self.midi_channel = midi_channel

    def set_value(self, value):
        self.enabled = (value < 1)
        self._set_led(self.enabled)

    def _set_led(self, enabled):
        if self.led_pin is not None:
            GPIO.output(self.led_pin, enabled)

    def set_lcd_color(self, color):
        self.lcd_color = color

    def pressed(self, short):
        # If a footswitch can be mapped to control a relay, preset, MIDI or all 3
        #
        # The footswitch will only "toggle" if it's associated with a relay
        # (in which case it will toggle with the relay) or with a Midi message
        #
        new_enabled = not self.enabled

        # Update Relay (if relay is associated with this footswitch)
        if len(self.relay_list) > 0:
            if short is False:
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
                return

        # If mapped to preset change
        if self.preset_callback is not None:
            # Change the preset and exit this method. Don't flip "enabled" since
            # there is no "toggle" action associated with a preset
            self.preset_callback()
            return

        # Send midi
        if self.midi_CC is not None:
            self.enabled = new_enabled
            # Update LED
            self._set_led(self.enabled)
            cc = [self.midi_channel | CONTROL_CHANGE, self.midi_CC, 127 if self.enabled else 0]
            logging.debug("Sending CC event: %d %s" % (self.midi_CC, self.fs_pin))
            self.midiout.send_message(cc)

        # Update plugin parameter if any
        if self.parameter is not None:
            self.parameter.value = not self.enabled  # TODO assumes mapped parameter is :bypass

        # Update LCD
        self.refresh_callback()

    def set_display_label(self, label):
        self.display_label = label

    def clear_display_label(self):
        self.display_label = None

    def add_relay(self, relay):
        self.relay_list.append(relay)
        self.set_value(not relay.init_state())

    def clear_relays(self):
        self.relay_list.clear()

    def add_preset(self, callback):
        self.preset_callback = callback

    def clear_preset(self):
        self.preset_callback = None
