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

from rtmidi.midiconstants import CONTROL_CHANGE

import common.util as util
import pistomp.controller as controller
import pistomp.encoder as encoder

import logging


class EncoderMidiControl(encoder.Encoder, controller.Controller):

    def __init__(self, handler, d_pin, clk_pin, callback, use_interrupt, midi_CC, midi_channel, midiout):
        super(EncoderMidiControl, self).__init__(d_pin=d_pin, clk_pin=clk_pin, callback=callback,
                                                 use_interrupt=use_interrupt, midi_CC=midi_CC,
                                                 midi_channel=midi_channel)
        self.handler = handler
        self.midi_CC = midi_CC
        self.midi_channel = midi_channel
        self.midiout = midiout

        self.value = 0       # the user view of the value
        self.midi_value = 0  # the midi equivalent value
        self.per_click = 8   # resolution (midi values per click)

        # Override base class to call our update function
        self.callback = self.refresh

    def set_midi_channel(self, midi_channel):
        self.midi_channel = midi_channel

    def set_value(self, value):
        # This gets called during pedalboard load (binding) to initialize the control position
        # TODO call this during snapshot/preset load as well, otherwise initial setting comes from previous snapshot
        self.value = value

        # determine equivalent (scaled) midi value based on param min and max
        if self.parameter.maximum >= value >= self.parameter.minimum:
            self.midi_value = util.renormalize(value, self.parameter.minimum, self.parameter.maximum, self.midi_min,
                                               self.midi_max)
        else:
            # LAME just set to 50%
            self.midi_value = 64

    def read_rotary(self):
        # base class read_rotary reads then calls callback which we set above to be this refresh()
        super().read_rotary()

    # Override of base class method
    def refresh(self, direction):
        midi_value = self.midi_value + (direction * self.per_click)

        # Keep midi value within limits
        if midi_value > self.midi_max:
            midi_value = self.midi_max
        if midi_value < self.midi_min:
            midi_value = self.midi_min

        cc = [self.midi_channel | CONTROL_CHANGE, self.midi_CC, midi_value]
        logging.debug("Encoder Sending CC event %s" % cc)
        self.midiout.send_message(cc)

        # Now that the MIDI msg was sent, update our current value
        self.midi_value = midi_value

        # Display
        self.handler.parameter_midi_change(self.parameter, direction) # TODO LAME object linkage


