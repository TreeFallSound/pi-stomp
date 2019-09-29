#!/usr/bin/env python3

import atexit
import json
import os
import requests as req
import RPi.GPIO as GPIO
import sys
import time

from rtmidi.midiutil import open_midiinput
from rtmidi.midiutil import open_midioutput
from rtmidi.midiconstants import (CONTROLLER_CHANGE, PROGRAM_CHANGE)

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
# the GPIO pin it's attached to, the associated LED output pin and
# the MIDI Control (CC) message that will be send when the switch is toggled
# Pin changes should only be made if the hardware is changed accordingly
FOOTSW = ((23, 24, 61), (25, 0, 62), (33, 26, 63))
FOOTSW_BYPASS_INDEX = 0


def preset_change(channel):
    global current_preset_index

    enc = GPIO.input(PRESET_PIN_D)
    index = (current_preset_index + 1) if (enc == 1) else (current_preset_index - 1)
    print("preset change: %d" % index)
    url = "http://localhost/pedalpreset/load?id=%d" % index
    print(url)
    # req.get("http://localhost/reset")
    resp = req.get(url)
    if resp.status_code != 200:
        print("Bad Rest request: %s status: %d" % (url, resp.status_code))
    current_preset_index = index


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

    mod = Mod.Mod()
    mod.load_pedalboards()
    mod.pedalboard_init()
    pb_name = mod.get_current_pedalboard_name()
    print("pb: %s" % pb_name)

    # Pedalboard info
    pb_info = lilv.get_pedalboard_info(mod.get_current_pedalboard())
    print(pb_info)
    param_list = list()
    for key, param in pb_info.items():
       if param != {}:
            p = param['instance'].capitalize() + ":" + param['parameter'].upper()
            print(p)
            param_list.append(p)
    print(len(param_list))

    lcd = Gfx.Gfx()
    lcd.draw_text_rows(pb_name)
    lcd.draw_bargraph(97)


    GPIO.setmode(GPIO.BCM)  # TODO should this go earlier?

    # FORCE RELAY ON
    #GPIO.setup(16, GPIO.OUT)
    #GPIO.output(16, GPIO.LOW)

    GPIO.setup(PRESET_PIN_CLK, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PRESET_PIN_D, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.add_event_detect(PRESET_PIN_CLK, GPIO.FALLING, callback=preset_change, bouncetime=300)

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

    print("Entering main loop. Press Control-C to exit.")
    try:
        while True:
            time.sleep(0.40)
    except KeyboardInterrupt:
        print('')
    finally:
        print("Exit.")
        midiout.close_port()
        #midiin.close_port()
        # del midiin
        lcd.clear()
        GPIO.cleanup()


if __name__ == '__main__':
    main()
