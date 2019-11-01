#!/usr/bin/env python3

import busio
import digitalio
import board
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn

from rtmidi.midiutil import open_midioutput
from rtmidi.midiconstants import CONTROL_CHANGE


class AnalogControl:

    def __init__(self, spi, adc_channel, midi_CC, tolerence, midi_channel, midiout):

        self.spi = spi
        self.adc_channel = adc_channel
        self.midi_CC = midi_CC
        self.midiout = midiout
        self.midi_channel = midi_channel
        self.last_read = 0          # this keeps track of the last potentiometer value
        self.tolerance = tolerence  # to keep from being jittery we'll only change the
                                    # value when the control has moved a significant amount

    def remap_range(self, value, left_min, left_max, right_min, right_max):
        # this remaps a value from original (left) range to new (right) range
        # Figure out how 'wide' each range is
        left_span = left_max - left_min
        right_span = right_max - right_min

        # Convert the left range into a 0-1 range (int)
        valueScaled = int(value - left_min) / int(left_span)

        # Convert the 0-1 range into a value in the right range.
        return int(right_min + (valueScaled * right_span))

    def readChannel(self):
        adc = self.spi.xfer2([1, (8 + self.adc_channel) << 4, 0])
        data = ((adc[1] & 3) << 8) + adc[2]
        return data

    def refresh(self):
        value_changed = False

        # read the analog pin
        value = self.readChannel()
        #print(value)

        # how much has it changed since the last read?
        pot_adjust = abs(value - self.last_read)

        if pot_adjust > self.tolerance:
            value_changed = True

        if value_changed:
            # convert 16bit adc0 (0-65535) trim pot read into 0-100 volume level
            set_volume = self.remap_range(value, 0, 1023, 0, 127)

            cc = [self.midi_channel | CONTROL_CHANGE, self.midi_CC, set_volume]
            print("AnalogControl Sending CC event %s" % cc)
            self.midiout.send_message(cc)

            # save the potentiometer reading for the next loop
            self.last_read = value