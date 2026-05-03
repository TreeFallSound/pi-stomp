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

"""EmulatorMod — Mod subclass for the v1 emulator.

Inherits the full v1 dual-encoder state machine from modalapi.Mod.
Overrides Pi-only I/O (wifi, system info, shutdown/reboot) and wires
pygame rendering into the poll loop.

Requires MOD Desktop running locally at http://127.0.0.1:18181.
"""

import logging
import os

from modalapi.mod import Mod
from emulator.stubs import VirtualAudiocard, StubWifiManager


class EmulatorMod(Mod):

    def __init__(self, homedir):
        import modalapi.wifi as _wifi_module
        _orig_wm = _wifi_module.WifiManager
        _wifi_module.WifiManager = lambda *a, **kw: StubWifiManager()
        try:
            super().__init__(VirtualAudiocard(), homedir)
        finally:
            _wifi_module.WifiManager = _orig_wm

        emu_data_dir = os.path.join(os.path.expanduser("~"), ".pistomp_emulator")
        self.pedalboard_modification_file = os.path.join(emu_data_dir, "last.json")
        self.pedalboard_change_timestamp = 0

        self.root_uri = "http://127.0.0.1:18181/"
        self._window = None

    def set_window(self, window):
        self._window = window

    # -------------------------------------------------------------------------
    # Skip Pi-only system calls
    # -------------------------------------------------------------------------

    def poll_wifi(self):
        pass

    def poll_system_info(self):
        pass

    def system_info_load(self):
        self.eq_status = self.audiocard.get_switch_parameter(self.audiocard.DAC_EQ)
        self.lcd.update_eq(self.eq_status)

    # -------------------------------------------------------------------------
    # System menu: shutdown exits the emulator; everything else is a no-op
    # -------------------------------------------------------------------------

    def system_menu_shutdown(self):
        logging.info("Emulator shutdown requested")
        raise KeyboardInterrupt

    def system_menu_reboot(self):
        logging.info("Emulator: reboot is a no-op")

    def system_menu_restart_sound(self):
        logging.info("Emulator: restart sound is a no-op")

    def system_menu_reload(self):
        logging.info("Emulator: reload configs is a no-op")

    # -------------------------------------------------------------------------
    # Window integration — drain events every tick; couple LCD flush +
    # window repaint to poll_lcd_updates so the emulator respects the main
    # loop's gating instead of rendering at ~100 fps.
    # -------------------------------------------------------------------------

    def poll_controls(self):
        if self._window is not None:
            self._window.process_events()
        super().poll_controls()

    def poll_lcd_updates(self):
        if self.lcd is not None:
            self.lcd.poll_updates()
        if self._window is not None:
            self._window.render()


    def cleanup(self):
        super().cleanup()
        import pygame
        pygame.quit()
