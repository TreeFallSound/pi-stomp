#!/usr/bin/env python3

# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.
import argparse
import logging
import os
import RPi.GPIO as GPIO
import sys
import time

from rtmidi.midiutil import open_midioutput

import pistomp.audiocardfactory as Audiocardfactory
import pistomp.config as config
import pistomp.generichost as Generichost
import pistomp.testhost as Testhost
import pistomp.handlerfactory as Handlerfactory
import pistomp.hardwarefactory as Hardwarefactory


def main():
    sys.settrace

    # Command line parsing
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", "-l", nargs='+', help="Provide logging level. Example --log debug'", default="info",
                        choices=['debug', 'info', 'warning', 'error', 'critical'])
    parser.add_argument("--host", nargs='+', help="Plugin host to use. Example --host mod'", default=['mod'],
                        choices=['mod', 'mod1', 'generic', 'test'])

    args = parser.parse_args()

    # Handle Log Level
    level_config = {'debug': logging.DEBUG, 'info': logging.INFO, 'warning': logging.WARNING, 'error': logging.ERROR,
                    'critical': logging.CRITICAL}
    log = args.log[0]
    log_level = level_config[log] if log in level_config else None
    if log_level:
        print("Log level now set to: %s" % logging.getLevelName(log_level))
        logging.basicConfig(level=log_level)

    # Current Working Dir
    cwd = os.path.dirname(os.path.realpath(__file__))

    # Audio Card Config - doing this early so audio passes ASAP
    factory = Audiocardfactory.Audiocardfactory(cwd)
    audiocard = factory.create()
    audiocard.restore() 

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

    # Handler object
    handler = None

    # Load the default config
    # cfg used by factories to determine which handler and hardware objects to create
    # Hardware object uses cfg to know how to initialize the hardware elements
    cfg = config.load_default_cfg()

    if args.host[0] == 'mod':

        # Create singleton Mod handler
        handlerfactory = Handlerfactory.Handlerfactory()
        handler = handlerfactory.create(cfg, audiocard, cwd)
        if handler is None:
            logging.error("Cannot create handler for the version specified in configuration file")
            sys.exit()

        # Initialize hardware (Footswitches, Encoders, Analog inputs, etc.)
        factory = Hardwarefactory.Hardwarefactory()
        hw = factory.create(cfg, handler, midiout)
        handler.add_hardware(hw)

        # Load all pedalboard info from the lilv ttl file
        handler.load_pedalboards()

        # Load the current pedalboard as "current"
        current_pedal_board_bundle = handler.get_current_pedalboard_bundle_path()
        if not current_pedal_board_bundle:
            # Apparently, no pedalboard is currently loaded so just change to the default
            handler.pedalboard_change()
        else:
            handler.set_current_pedalboard(handler.pedalboards[current_pedal_board_bundle])

        # Load system info.  This can take a few seconds
        handler.system_info_load()

    elif args.host[0] == 'generic':
        # No specific plugin host specified, so use a generic handler
        # Encoders and LCD not mapped without specific purpose
        # Just initialize the control hardware (footswitches, analog controls, etc.) for use as MIDI controls
        handler = Generichost.Generichost(homedir=cwd)
        factory = Hardwarefactory.Hardwarefactory()
        hw = factory.create(cfg, handler, midiout)
        handler.add_hardware(hw)

    elif args.host[0] == 'test':
        handler = Testhost.Testhost(audiocard, homedir=cwd)
        try:
            factory = Hardwarefactory.Hardwarefactory()
            hw = factory.create(cfg, handler, midiout)
            handler.add_hardware(hw)
        except:
            raise

    logging.info("Entering main loop. Press Control-C to exit.")
    period = 0
    try:
        while True:
            handler.poll_controls()
            time.sleep(0.01)  # lower to increase responsiveness, but can cause conflict with LCD if too low

            # For less frequent events
            period += 1
            if period % 2 == 0:
                handler.poll_indicators()
            if period % 20 == 0:
                handler.poll_lcd_updates()
            if period > 100:
                handler.poll_modui_changes()
                period = 0

    except KeyboardInterrupt:
        logging.info('keyboard interrupt')
    finally:
        logging.info("Exit.")
        midiout.close_port()
        handler.cleanup()
        GPIO.cleanup()
        del handler
        logging.info("Completed cleanup")


if __name__ == '__main__':
    main()
