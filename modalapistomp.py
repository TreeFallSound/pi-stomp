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

# Configure logging BEFORE any imports to ensure it takes effect
import logging
import sys
from typing import Any

# Set up logging with format that works well with systemd journal
logging.basicConfig(
    level=logging.INFO,  # Default level, will be overridden by CLI arg
    format="%(levelname)s:%(name)s:%(message)s",
    stream=sys.stderr,
)

import argparse
import os
import time

from rtmidi.midiutil import open_midioutput

from pistomp.audiocard import Audiocard
import pistomp.audiocardfactory as Audiocardfactory
import pistomp.config as config
import pistomp.generichost as Generichost
import pistomp.testhost as Testhost
import pistomp.handlerfactory as Handlerfactory
import pistomp.hardwarefactory as Hardwarefactory

EMULATOR_CONFIG_TEMPLATE = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "setup", "config_templates", "default_config_pistomptre.yml"
)
EMULATOR_V2_CONFIG_TEMPLATE = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "setup", "config_templates", "default_config_pistompcore.yml"
)
EMULATOR_V1_CONFIG_TEMPLATE = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "setup", "config_templates", "default_config_pistomp.yml"
)


def main():
    sys.settrace

    # Command line parsing
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--log",
        "-l",
        nargs="+",
        help="Provide logging level. Example --log debug'",
        default="info",
        choices=["debug", "info", "warning", "error", "critical"],
    )
    parser.add_argument(
        "--host",
        nargs="+",
        help="Plugin host to use. Example --host mod'",
        default=["mod"],
        choices=["mod", "mod1", "generic", "test", "emulator_v1", "emulator_v2", "emulator_v3"],
    )
    parser.add_argument(
        "--tuner-source",
        default=None,
        help="Audio source for tuner: 'jack' or 'tone:<hz>' (e.g. tone:440). Defaults to 'tone:440' on emulator, 'jack' otherwise.",
    )

    args = parser.parse_args()

    # Handle Log Level - override the default INFO level set at startup
    level_config = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }
    log = args.log[0]
    log_level = level_config[log] if log in level_config else None
    if log_level:
        print("Log level now set to: %s" % logging.getLevelName(log_level))
        logging.getLogger().setLevel(log_level)

    # Disable websockets library debug logging (too noisy)
    logging.getLogger('websockets').setLevel(logging.WARNING)

    # Current Working Dir
    cwd = os.path.dirname(os.path.realpath(__file__))

    # Handler object
    handler = None
    midiout = None

    cfg: dict[str, Any] | None = None
    audiocard: Audiocard | None = None

    if args.host[0] not in ("emulator_v1", "emulator_v2", "emulator_v3"):
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
        port = 0  # TODO get this (the Midi Through port) programmatically
        # port = sys.argv[1] if len(sys.argv) > 1 else None
        try:
            midiout, port_name = open_midioutput(port)
        except (EOFError, KeyboardInterrupt):
            sys.exit()

        # Load the default config
        # cfg used by factories to determine which handler and hardware objects to create
        # Hardware object uses cfg to know how to initialize the hardware elements
        cfg = config.load_default_cfg()

    if args.host[0] == "mod":
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

        # Configure pedalboards git remote if specified in default_config.yml
        url = cfg.get('pedalboards')
        if url:
            handler.init_pedalboards_remote(url)

        # Load all pedalboard info from the lilv ttl file
        handler.load_banks()
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

    elif args.host[0] == "generic":
        # No specific plugin host specified, so use a generic handler
        # Encoders and LCD not mapped without specific purpose
        # Just initialize the control hardware (footswitches, analog controls, etc.) for use as MIDI controls
        handler = Generichost.Generichost(homedir=cwd)
        factory = Hardwarefactory.Hardwarefactory()
        hw = factory.create(cfg, handler, midiout)
        handler.add_hardware(hw)

    elif args.host[0] == "test":
        handler = Testhost.Testhost(audiocard, homedir=cwd)
        try:
            factory = Hardwarefactory.Hardwarefactory()
            hw = factory.create(cfg, handler, midiout)
            handler.add_hardware(hw)
        except:
            raise

    elif args.host[0] in ("emulator_v1", "emulator_v2", "emulator_v3"):
        import pygame
        import pygame._freetype as _freetype
        from emulator.window import EmulatorWindow

        _emu_version = args.host[0]  # "emulator_v1" / "emulator_v2" / "emulator_v3"

        if _emu_version == "emulator_v1":
            from emulator.hardware_v1 import EmulatorHardwareV1 as _EmuHW
            from emulator.mod import EmulatorMod as _EmuHandler
            _emu_cfg_template = EMULATOR_V1_CONFIG_TEMPLATE
        elif _emu_version == "emulator_v2":
            from emulator.hardware_v2 import EmulatorHardwareV2 as _EmuHW
            from emulator.modhandler import EmulatorModhandler as _EmuHandler
            _emu_cfg_template = EMULATOR_V2_CONFIG_TEMPLATE
        else:  # emulator_v3
            from emulator.hardware_v3 import EmulatorHardwareV3 as _EmuHW
            from emulator.modhandler import EmulatorModhandler as _EmuHandler
            _emu_cfg_template = EMULATOR_CONFIG_TEMPLATE

        pygame.init()
        _freetype.init()

        port = 0
        try:
            midiout, port_name = open_midioutput(port)
        except Exception:
            logging.warning("MIDI output unavailable in emulator mode - continuing without MIDI")
            midiout = None
        cfg = config.load_cfg_from_file(_emu_cfg_template)

        if _emu_version != "emulator_v1":
            import pistomp.settings as Settings_module
            emu_cfg_dir = os.path.join(os.path.expanduser("~"), ".pistomp_emulator", "config")
            os.makedirs(emu_cfg_dir, exist_ok=True)
            Settings_module.DATA_DIR = emu_cfg_dir

        handler = _EmuHandler(cwd)
        hw = _EmuHW(cfg, handler, midiout, refresh_callback=handler.update_lcd_fs)
        handler.add_hardware(hw)

        window = EmulatorWindow(hw)
        handler.set_window(window)

        handler.load_banks()
        handler.load_pedalboards()

        current_bundle = handler.get_current_pedalboard_bundle_path()
        if current_bundle and current_bundle in handler.pedalboards:
            handler.set_current_pedalboard(handler.pedalboards[current_bundle])
        else:
            handler.pedalboard_change()

        handler.system_info_load()

    assert handler is not None

    # Wire tuner source factory if the handler supports it
    if hasattr(handler, "set_tuner_source_factory"):
        _is_emulator = args.host[0] in ("emulator_v1", "emulator_v2", "emulator_v3")
        if _is_emulator:
            from pistomp.tuner.source import ToneSweepSource
            handler.set_tuner_source_factory(ToneSweepSource)
        else:
            from pistomp.tuner.source import build_source
            _tuner_spec = args.tuner_source or "jack"
            handler.set_tuner_source_factory(lambda: build_source(_tuner_spec))

    logging.info("Entering main loop. Press Control-C to exit.")
    period = 0
    try:
        # startup actions
        handler.poll_system_info()

        # main loop
        while True:
            handler.poll_controls()
            time.sleep(0.01)  # lower to increase responsiveness, but can cause conflict with LCD if too low

            # For less frequent events
            period += 1
            if period % 2 == 0:
                handler.poll_indicators()
            # LCD polling frequency adapts to SPI speed (24MHz→80ms, 48MHz→40ms, 56MHz→30ms)
            if period % handler.lcd_poll_divisor == 0:
                handler.poll_lcd_updates()
            if period % 100 == 0:
                handler.poll_modui_changes()
            if period % 200 == 0:
                handler.poll_wifi()
            if period > 6000:  # every 60 seconds (when sleep = 0.01)
                handler.poll_system_info()
                period = 0

    except KeyboardInterrupt:
        logging.info("keyboard interrupt")
    finally:
        logging.info("Exit.")
        if midiout:
            midiout.close_port()
        handler.cleanup()
        del handler
        logging.info("Completed cleanup")


if __name__ == "__main__":
    main()
