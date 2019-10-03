#!/usr/bin/env python3

import busio
import digitalio
import board
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn

from rtmidi.midiutil import open_midioutput
from rtmidi.midiconstants import CONTROL_CHANGE


class AnalogControl:

    def __init__(self, midi_CC, midiout):

        self.midi_CC = midi_CC
        self.midiout = midiout

        # create the spi bus
        spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)

        # create the cs (chip select)
        cs = digitalio.DigitalInOut(board.D7)

        # create the mcp object
        self.mcp = MCP.MCP3008(spi, cs)

        # create an analog input channel on pin 0  TODO this should be a dynamic list
        self.chan0 = AnalogIn(self.mcp, MCP.P0)
        self.chan1 = AnalogIn(self.mcp, MCP.P1)

        self.last_read = 0       # this keeps track of the last potentiometer value
        self.tolerance = 250     # to keep from being jittery we'll only change
                    # volume when the pot has moved a significant amount
                    # on a 16-bit ADC

    def remap_range(self, value, left_min, left_max, right_min, right_max):
        # this remaps a value from original (left) range to new (right) range
        # Figure out how 'wide' each range is
        left_span = left_max - left_min
        right_span = right_max - right_min

        # Convert the left range into a 0-1 range (int)
        valueScaled = int(value - left_min) / int(left_span)

        # Convert the 0-1 range into a value in the right range.
        return int(right_min + (valueScaled * right_span))

    def refresh(self):
        trim_pot_changed = False

        # read the analog pin
        trim_pot = self.chan0.value

        # read the pb switch (pullup with 10k)
        pb = self.chan1.value
        if pb < 22000:
            print(pb)

        # how much has it changed since the last read?
        pot_adjust = abs(trim_pot - self.last_read)

        if pot_adjust > self.tolerance:
            trim_pot_changed = True

        if trim_pot_changed:
            # convert 16bit adc0 (0-65535) trim pot read into 0-100 volume level
            set_volume = self.remap_range(trim_pot, 0, 65535, 0, 127)

            cc = [CONTROL_CHANGE, self.midi_CC, set_volume]
            print("Sending CC event %d" % set_volume)
            self.midiout.send_message(cc)

            # save the potentiometer reading for the next loop
            self.last_read = trim_pot
