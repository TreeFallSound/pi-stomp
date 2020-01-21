#!/usr/bin/env python3

import busio
import digitalio
import board
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn
from enum import Enum


import modalapi.analogcontrol as analogcontrol

class Value(Enum):
    DEFAULT = 0
    PRESSED = 1
    RELEASED = 2
    LONGPRESSED = 3
    CLICKED = 4
    DOUBLECLICKED = 5

LONGPRESS_THRESHOLD = 60  # TODO somewhat LAME.  It's dependent on the refresh frequency of the main loop

class AnalogSwitch(analogcontrol.AnalogControl):

    def __init__(self, spi, adc_channel, tolerance, callback):
        super(AnalogSwitch, self).__init__(spi, adc_channel, tolerance)
        self.last_read = None          # this keeps track of the last value
        self.trigger_count = 0
        self.callback = callback
        self.longpress_state = False

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

        # Count the number of simultaneous refresh cycles had the switch Low (triggered)
        if not self.longpress_state and value < self.tolerance and self.last_read < self.tolerance:
            self.trigger_count += 1
            if self.trigger_count > LONGPRESS_THRESHOLD:
                value_changed = True
                self.longpress_state = True

        if value_changed:

            # save the potentiometer reading for the next loop
            self.last_read = value

            if self.trigger_count > LONGPRESS_THRESHOLD:
                value = Value.LONGPRESSED
            elif value < self.tolerance:
                value = Value.PRESSED
            elif value >= self.tolerance:
                if self.longpress_state:
                    self.longpress_state = False
                    self.trigger_count = 0
                    return
                else:
                    value = Value.RELEASED
            self.trigger_count = 0

            self.callback(value)
