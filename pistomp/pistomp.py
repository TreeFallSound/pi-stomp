#!/usr/bin/env python3

# This subclass defines hardware specific to pi-stomp! v1
# 3 Footswitches
# 1 Analog Pot
# 1 Expression Pedal
# 2 Encoders with switches
#
# A new version with different controls should have a new separate subclass

import RPi.GPIO as GPIO
import logging
import json
import spidev

import pistomp.analogmidicontrol as AnalogMidiControl
import pistomp.analogswitch as AnalogSwitch
import pistomp.controller as Controller
import pistomp.encoder as Encoder
import pistomp.footswitch as Footswitch
import pistomp.hardware as hardware
import pistomp.relay as Relay
import modalapi.util as util

# Pins
TOP_ENC_PIN_D = 17
TOP_ENC_PIN_CLK = 4
TOP_ENC_SWITCH_CHANNEL = 7
BOT_ENC_PIN_D = 22
BOT_ENC_PIN_CLK = 27
BOT_ENC_SWITCH_CHANNEL = 6
ENC_SW_THRESHOLD = 512

RELAY_RESET_PIN = 16
RELAY_SET_PIN = 12

# Each footswitch defined by a quad touple:
# 1: id (left = 0, mid = 1, right = 2)
# 2: the GPIO pin it's attached to
# 3: the associated LED output pin and
# 4: the MIDI Control (CC) message that will be sent when the switch is toggled
# Pin modifications should only be made if the hardware is changed accordingly
FOOTSW = ((0, 23, 24, 61), (1, 25, 0, 62), (2, 13, 26, 63))

# TODO replace in default_config.yml
# Analog Controls defined by a triple touple:
# 1: the ADC channel
# 2: the minimum threshold for considering the value to be changed
# 3: the MIDI Control (CC) message that will be sent
# 4: control type (KNOB, EXPRESSION, etc.)
# Tweak, Expression Pedal
ANALOG_CONTROL = ((0, 16, 64, 'KNOB'), (1, 16, 65, 'EXPRESSION'))

class Pistomp(hardware.Hardware):
    __single = None

    def __init__(self, mod, midiout, refresh_callback):
        super(Pistomp, self).__init__(mod, midiout, refresh_callback)
        if Pistomp.__single:
            raise Pistomp.__single
        Pistomp.__single = self

        GPIO.setmode(GPIO.BCM)

        # Create Relay object(s)
        #self.relay = Relay.Relay(RELAY_RESET_PIN, RELAY_SET_PIN)
        self.relay = Relay.Relay(RELAY_SET_PIN, RELAY_RESET_PIN)

        # Create Footswitches
        for f in FOOTSW:
            fs = Footswitch.Footswitch(f[0], f[1], f[2], f[3], self.midi_channel, midiout,
                                       refresh_callback=self.refresh_callback)
            self.footswitches.append(fs)
        self.reinit(None)

        # Initialize Analog inputs
        spi = spidev.SpiDev()
        spi.open(0, 1)  # Bus 0, CE1
        spi.max_speed_hz = 1000000  # TODO match with LCD or don't specify.  Move to top of file
        for c in ANALOG_CONTROL:
            control = AnalogMidiControl.AnalogMidiControl(spi, c[0], c[1], c[2], self.midi_channel, midiout, c[3])
            self.analog_controls.append(control)
            key = format("%d:%d" % (self.midi_channel, c[2]))
            self.controllers[key] = control  # Controller.Controller(self.midi_channel, c[1], Controller.Type.ANALOG)

        # Initialize Encoders
        top_enc = Encoder.Encoder(TOP_ENC_PIN_D, TOP_ENC_PIN_CLK, callback=mod.top_encoder_select)
        self.encoders.append(top_enc)
        bot_enc = Encoder.Encoder(BOT_ENC_PIN_D, BOT_ENC_PIN_CLK, callback=mod.bot_encoder_select)
        self.encoders.append(bot_enc)
        control = AnalogSwitch.AnalogSwitch(spi, TOP_ENC_SWITCH_CHANNEL, ENC_SW_THRESHOLD, callback=mod.top_encoder_sw)
        self.analog_controls.append(control)
        control = AnalogSwitch.AnalogSwitch(spi, BOT_ENC_SWITCH_CHANNEL, ENC_SW_THRESHOLD, callback=mod.bottom_encoder_sw)
        self.analog_controls.append(control)
