#!/usr/bin/env python3

#import busio
#import digitalio
#import board
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn

from rtmidi.midiutil import open_midioutput
from rtmidi.midiconstants import CONTROL_CHANGE

import modalapi.analogcontrol as analogcontrol
import modalapi.util as util

import logging


class AnalogMidiControl(analogcontrol.AnalogControl):

    def __init__(self, spi, adc_channel, tolerance, midi_CC, midi_channel, midiout, type):
        super(AnalogMidiControl, self).__init__(spi, adc_channel, tolerance)
        self.midi_CC = midi_CC
        self.midiout = midiout
        self.midi_channel = midi_channel

        # Parent member overrides
        self.type = type
        self.last_read = 0          # this keeps track of the last potentiometer value
        self.value = None

    def set_midi_channel(self, midi_channel):
        self.midi_channel = midi_channel

    def set_value(self, value):
        self.value = value

    # Override of base class method
    def refresh(self):
        # read the analog pin
        value = self.readChannel()

        # how much has it changed since the last read?
        pot_adjust = abs(value - self.last_read)
        value_changed = (pot_adjust > self.tolerance)

        if value_changed:
            # convert 16bit adc0 (0-65535) trim pot read into 0-100 volume level
            set_volume = util.renormalize(value, 0, 1023, 0, 127)

            cc = [self.midi_channel | CONTROL_CHANGE, self.midi_CC, set_volume]
            logging.debug("AnalogControl Sending CC event %s" % cc)
            self.midiout.send_message(cc)

            # save the potentiometer reading for the next loop
            self.last_read = value
