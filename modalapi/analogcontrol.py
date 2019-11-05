#!/usr/bin/env python3

import busio
import digitalio
import board
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn


class AnalogControl:

    def __init__(self, spi, adc_channel, tolerance):

        self.spi = spi
        self.adc_channel = adc_channel
        self.last_read = 0          # this keeps track of the last potentiometer value
        self.tolerance = tolerance  # to keep from being jittery we'll only change the
                                    # value when the control has moved a significant amount

    def readChannel(self):
        adc = self.spi.xfer2([1, (8 + self.adc_channel) << 4, 0])
        data = ((adc[1] & 3) << 8) + adc[2]
        return data

    def refresh(self):
        print("AnalogControl subclass hasn't overriden the refresh method")
