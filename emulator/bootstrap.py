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

import logging
import os
from typing import Literal

from rtmidi.midiutil import open_midioutput

import pistomp.config as config

EmulatorVersion = Literal["emulator_v1", "emulator_v2", "emulator_v3"]

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
_CONFIG_TEMPLATES = {
    "emulator_v1": os.path.join(_REPO_ROOT, "setup", "config_templates", "default_config_pistomp.yml"),
    "emulator_v2": os.path.join(_REPO_ROOT, "setup", "config_templates", "default_config_pistompcore.yml"),
    "emulator_v3": os.path.join(_REPO_ROOT, "setup", "config_templates", "default_config_pistomptre.yml"),
}


def bootstrap_emulator(version: EmulatorVersion, cwd: str):
    """Initialize pygame, build the emulator handler/hardware, and return (handler, midiout)."""
    import pygame
    import pygame._freetype as _freetype
    from emulator.window import EmulatorWindow

    match version:
        case "emulator_v1":
            from emulator.hardware_v1 import EmulatorHardwareV1 as EmuHW
            from emulator.mod import EmulatorMod as EmuHandler
        case "emulator_v2":
            from emulator.hardware_v2 import EmulatorHardwareV2 as EmuHW
            from emulator.modhandler import EmulatorModhandler as EmuHandler
        case "emulator_v3":
            from emulator.hardware_v3 import EmulatorHardwareV3 as EmuHW
            from emulator.modhandler import EmulatorModhandler as EmuHandler

    pygame.init()
    _freetype.init()

    try:
        midiout, _port_name = open_midioutput(0)
    except Exception:
        logging.warning("Disabled: MIDI output unavailable in emulator mode")
        midiout = None

    cfg = config.load_cfg_from_file(_CONFIG_TEMPLATES[version])

    handler = EmuHandler(cwd)
    hw = EmuHW(cfg, handler, midiout, refresh_callback=handler.update_lcd_fs)
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

    return handler, midiout
