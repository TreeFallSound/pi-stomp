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
        self.last_read = 0          # this keeps track of the last value
        self.callback = callback

    # Override of base class method
    def refresh(self):
        value_changed = False

        # read the analog pin
        value = self.readChannel()

        # how much has it changed since the last read?
        pot_adjust = abs(value - self.last_read)

        if pot_adjust > self.tolerance:
            value_changed = True

        if value_changed:
            # save the potentiometer reading for the next loop
            self.last_read = value

            self.callback(value)
