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
import modalapi.mod as Mod


def main():
    # MIDI initialization
    # Prompts user for MIDI input port, unless a valid port number or name
    # is given as the first argument on the command line.
    # API backend defaults to ALSA on Linux.
    # TODO discover and use the thru port (seems to be 14:0 on my system)
    # shouldn't need to aconnect, just send msgs directly to the thru port
    port = 0 # TODO get this (the Midi Through port) programmatically
    #port = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        midiout, port_name = open_midioutput(port)
    except (EOFError, KeyboardInterrupt):
        sys.exit()

    lcd = Gfx.Gfx()

    # Create singleton data model object
    mod = Mod.Mod(lcd)

    # Initialize hardware (Footswitches, Encoders, Analog inputs, etc.)
    hw = Hardware.Hardware(mod, midiout, refresh_callback=mod.update_lcd_fs)
    mod.add_hardware(hw)

    # Load all pedalboard info from the lilv ttl file
    mod.load_pedalboards()

    # Load the current pedalboard as "current"
    current_pedal_board_bundle = mod.get_current_pedalboard_bundle_path()
    if not current_pedal_board_bundle:
        # Apparently, no pedalboard is currently loaded so just load the first one
        current_pedal_board_bundle = list(mod.pedalboards.keys())[0]
    mod.set_current_pedalboard(mod.pedalboards[current_pedal_board_bundle])


    # Load LCD
    #mod.update_lcd()
    #touch.set_led(0, 1)
    #touch.set_led(2, 1)

    print("Entering main loop. Press Control-C to exit.")
    #period = 0
    try:
        while True:
            for c in hw.analog_controls:
                c.refresh()
            time.sleep(0.01)  # TODO less to increase responsiveness

            # For less frequent events
            # period += 1
            # if period > 100:
            #     period = 0


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
