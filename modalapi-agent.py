#!/usr/bin/env python3

import atexit
import json
import os
import requests as req
import RPi.GPIO as GPIO
import spidev
import sys
import time

from rtmidi.midiutil import open_midiinput
from rtmidi.midiutil import open_midioutput
from rtmidi.midiconstants import (CONTROLLER_CHANGE, PROGRAM_CHANGE)


import modalapi.analogcontrol as AnalogControl
import modalapi.encoder as Encoder
import modalapi.footswitch as Footswitch
import modalapi.gfx as Gfx
import modalapi.lilv as lilv
import modalapi.mod as Mod
import modalapi.relay as Relay

# Pins
PRESET_PIN_D = 22
PRESET_PIN_CLK = 27

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


# TODO move to mod lib
def find_input(inputs, symbol):
    for i in inputs:
        sym = i['symbol']
        if sym == symbol:
            return i
    return None

def main():
    # MIDI initialization
    # Prompts user for MIDI input port, unless a valid port number or name
    # is given as the first argument on the command line.
    # API backend defaults to ALSA on Linux.
    # TODO discover and use the thru port (seems to be 14:0 on my system)
    # shouldn't need to aconnect, just send msgs directly to the thru port
    port = 0  # TODO
    #port = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        midiout, port_name = open_midioutput(port)
    except (EOFError, KeyboardInterrupt):
        sys.exit()

    lcd = Gfx.Gfx()

    mod = Mod.Mod(lcd)
    pedalboards = mod.load_pedalboards()
    mod.pedalboard_init()
    pb_name = mod.get_current_pedalboard_name()
    print("\npb: %s" % pb_name)


    # Load LCD
    text = "%s-%s" % (pb_name, mod.get_current_preset_name())
    lcd.draw_text_rows(text)
    lcd.draw_bargraph(97)


    GPIO.setmode(GPIO.BCM)  # TODO should this go earlier?

    # Initialize Encoders
    enc = Encoder.Encoder(PRESET_PIN_D, PRESET_PIN_CLK, callback=mod.preset_change)

    # Initialize Footswitches
    footsw_list = []
    for f in FOOTSW:
        fs = Footswitch.Footswitch(f[0], f[1], f[2], midiout)
        footsw_list.append(fs)

    # Initialize Relays
    # By default, associate with the footswitch identified by FOOT_BYPASS_INDEX
    # This can be user modified later
    relay_left = Relay.Relay(RELAY_LEFT_PIN)
    footsw_list[FOOTSW_BYPASS_INDEX].add_relay(relay_left)
    relay_right = Relay.Relay(RELAY_RIGHT_PIN)
    footsw_list[FOOTSW_BYPASS_INDEX].add_relay(relay_right)

    # Initialize Analog inputs
    spi = spidev.SpiDev()
    spi.open(0, 1)  # Bus 0, CE1
    spi.max_speed_hz = 1000000  # TODO match with LCD or don't specify
    control_list = []
    for c in ANALOG_CONTROL:
        control = AnalogControl.AnalogControl(spi, c[0], c[1], c[2], midiout)
        control_list.append(control)

    print("Entering main loop. Press Control-C to exit.")
    try:
        while True:
            for c in control_list:
                c.refresh()
            time.sleep(0.01)  # TODO less to increase responsiveness
    except KeyboardInterrupt:
        print('')
    finally:
        print("Exit.")
        midiout.close_port()
        #midiin.close_port()
        # del midiin
        lcd.cleanup()
        GPIO.cleanup()
        print("Completed cleanup")


if __name__ == '__main__':
    main()
