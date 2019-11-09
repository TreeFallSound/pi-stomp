#!/usr/bin/env python3

import busio
import digitalio
import board
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn

import modalapi.analogcontrol as analogcontrol


class AnalogSwitch(analogcontrol.AnalogControl):

    def __init__(self, spi, adc_channel, tolerance, callback):
        super(AnalogSwitch, self).__init__(spi, adc_channel, tolerance)
        self.last_read = None          # this keeps track of the last value
        self.callback = callback

    # Override of base class method
    def refresh(self):
        # read the analog pin
        value = self.readChannel()

        # if last read is None, this is the first refresh so don't do anything yet
        if self.last_read == None:
            self.last_read = value
            return

        # how much has it changed since the last read?
        pot_adjust = abs(value - self.last_read)
        value_changed = (pot_adjust > self.tolerance)

        if value_changed:
            # save the potentiometer reading for the next loop
            self.last_read = value
            self.callback(value)
