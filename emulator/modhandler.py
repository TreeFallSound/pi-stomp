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

"""EmulatorModhandler — Modhandler subclass for the v2/v3 emulator.

Inherits the modern uilib/lcd320x240 handler from modalapi.Modhandler.
Overrides Pi-only I/O (wifi, system info, shutdown/reboot) and wires
pygame rendering into the poll loop.

Requires MOD Desktop running locally at http://127.0.0.1:18181.
"""

import logging
import os

from modalapi.modhandler import Modhandler
from emulator.stubs import VirtualAudiocard, StubWifiManager


class EmulatorModhandler(Modhandler):

    def __init__(self, homedir):
        super().__init__(VirtualAudiocard(), homedir)

        emu_data_dir = os.path.join(os.path.expanduser("~"), ".pistomp_emulator")
        self.data_dir = emu_data_dir
        self.banks_file = os.path.join(emu_data_dir, "banks.json")
        self.pedalboard_modification_file = os.path.join(emu_data_dir, "last.json")
        self.pedalboard_change_timestamp = 0
        self.banks_file_timestamp = 0

        self.root_uri = "http://127.0.0.1:18181/"
        self.wifi_manager = StubWifiManager()

        self._window = None

    def set_window(self, window):
        self._window = window

    def pedalboard_change(self, pedalboard=None):
        if pedalboard is None and self.pedalboard_list:
            pedalboard = self.pedalboard_list[0]
        super().pedalboard_change(pedalboard)
        if pedalboard is not None:
            self.set_current_pedalboard(pedalboard)

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
        self.bypass_left = self.audiocard.get_bypass_left()
        self.bypass_right = self.audiocard.get_bypass_right()
        self.lcd.update_bypass(self.bypass_left, self.bypass_right)

    # -------------------------------------------------------------------------
    # System menu: shutdown exits the emulator; everything else is a no-op
    # -------------------------------------------------------------------------

    def system_menu_shutdown(self, arg):
        logging.info("Emulator shutdown requested")
        raise KeyboardInterrupt

    def system_menu_reboot(self, arg):
        logging.info("Emulator: reboot is a no-op")

    def system_menu_restart_sound(self, arg):
        logging.info("Emulator: restart sound is a no-op")

    def system_menu_reload(self, arg):
        logging.info("Emulator: reload configs is a no-op")

    def system_toggle_hotspot(self, **kwargs):
        pass

    def configure_wifi_credentials(self, ssid, password):
        return None

    # -------------------------------------------------------------------------
    # Window integration — drain events and repaint every poll_controls tick
    # (10 ms) to match the real device where lcd.update() is synchronous and
    # each widget refresh is immediately visible.  poll_lcd_updates is still
    # called for the lcd_needs_update full-screen path (panel transitions).
    # -------------------------------------------------------------------------

    def poll_controls(self):
        if self._window is not None:
            self._window.process_events()
            self._window.render()
        super().poll_controls()

    def poll_lcd_updates(self):
        super().poll_lcd_updates()
