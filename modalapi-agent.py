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

import modalapi.gfx as Gfx
import modalapi.hardware as Hardware
import modalapi.lilv as lilv
import modalapi.mod as Mod


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
    mod.load_pedalboards()
    #mod.pedalboard_init()  # TODO remove this mod-ui version that does the same as load_pedalboards()
    pb_name = mod.get_current_pedalboard_name()
    print("\npb: %s" % pb_name)

    # Load LCD
    text = "%s-%s" % (pb_name, mod.get_current_preset_name())
    lcd.draw_text_rows(text)
    #lcd.draw_bargraph(97)
    lcd.draw_plugins(mod.pedalboards[mod.get_current_pedalboard()].plugins)


    # Initialize hardware (Footswitches, Encoders, Analog inputs, etc.)
    hw = Hardware.Hardware(mod, midiout)

    print("Entering main loop. Press Control-C to exit.")
    try:
        while True:
            for c in hw.analog_controls:
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
