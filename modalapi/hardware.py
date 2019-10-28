#!/usr/bin/env python3

import RPi.GPIO as GPIO
import json
import spidev

import modalapi.analogcontrol as AnalogControl
import modalapi.controller as Controller
import modalapi.encoder as Encoder
import modalapi.footswitch as Footswitch
import modalapi.relay as Relay
import modalapi.util as util

# Midi
MIDI_CHANNEL = 3

# Pins
TOP_ENC_PIN_D = 17
TOP_ENC_PIN_CLK = 4
BOT_ENC_PIN_D = 22
BOT_ENC_PIN_CLK = 27

RELAY_LEFT_PIN = 16
RELAY_RIGHT_PIN = 12

# Each footswitch defined by a triple touple:
# 1: the GPIO pin it's attached to
# 2: the associated LED output pin and
# 3: the MIDI Control (CC) message that will be sent when the switch is toggled
# Pin modifications should only be made if the hardware is changed accordingly
FOOTSW = ((23, 24, 61), (25, 0, 62), (13, 26, 63))
FOOTSW_BYPASS_INDEX = 0

# Analog Controls defined by a triple touple:
# 1: the ADC channel
# 2: the MIDI Control (CC) message that will be sent
# 3: the minimum threshold for considering the value to be changed
# Tweak, Expression Pedal, Preset Encoder Switch, Nav Encoder Switch
ANALOG_CONTROL = ((0, 64, 16), (1, 65, 16), (6, 66, 512), (7, 67, 512))

class Hardware:
    __single = None

    def __init__(self, mod, midiout):
        print("Init hardware")
        if Hardware.__single:
            raise Hardware.__single
        Hardware.__single = self

        self.analog_controls = []
        self.controller = {}
        self.footswitches = []


        GPIO.setmode(GPIO.BCM)  # TODO should this go earlier?

        # Initialize Encoders
        top_enc = Encoder.Encoder(TOP_ENC_PIN_D, TOP_ENC_PIN_CLK, callback=mod.preset_change)
        bot_enc = Encoder.Encoder(BOT_ENC_PIN_D, BOT_ENC_PIN_CLK, callback=mod.preset_change)

        # Initialize Footswitches
        for f in FOOTSW:
            fs = Footswitch.Footswitch(f[0], f[1], f[2], midiout)
            self.footswitches.append(fs)
            key = format("%d:%d" % (MIDI_CHANNEL, f[1]))
            self.controller[key] = Controller.Controller(MIDI_CHANNEL, f[1], Controller.Type.FOOTSWITCH)

        # Initialize Relays
        # By default, associate with the footswitch identified by FOOT_BYPASS_INDEX
        # This can be user modified later
        relay_left = Relay.Relay(RELAY_LEFT_PIN)
        self.footswitches[FOOTSW_BYPASS_INDEX].add_relay(relay_left)
        relay_right = Relay.Relay(RELAY_RIGHT_PIN)
        self.footswitches[FOOTSW_BYPASS_INDEX].add_relay(relay_right)

        # Initialize Analog inputs
        spi = spidev.SpiDev()
        spi.open(0, 1)  # Bus 0, CE1
        spi.max_speed_hz = 1000000  # TODO match with LCD or don't specify.  Move to top of file
        for c in ANALOG_CONTROL:
            control = AnalogControl.AnalogControl(spi, c[0], c[1], c[2], midiout)
            self.analog_controls.append(control)
            key = format("%d:%d" % (MIDI_CHANNEL, c[1]))
            self.controller[key] = Controller.Controller(MIDI_CHANNEL, c[1], Controller.Type.ANALOG)

