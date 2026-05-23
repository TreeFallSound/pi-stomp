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
from modalapi.websocket_bridge import AsyncWebSocketBridge
import pistomp.settings as Settings
from emulator.stubs import VirtualAudiocard, StubWifiManager


class EmulatorModhandler(Modhandler):

    def __init__(self, homedir):
        super().__init__(VirtualAudiocard(), homedir)

        emu_data_dir = os.path.join(os.path.expanduser("~"), ".pistomp_emulator")
        os.makedirs(emu_data_dir, exist_ok=True)
        self.data_dir = emu_data_dir
        self.banks_file = os.path.join(emu_data_dir, "banks.json")
        self.pedalboard_modification_file = os.path.join(emu_data_dir, "last.json")
        self.pedalboard_change_timestamp = 0
        self.banks_file_timestamp = 0

        from modalapi.pedalboard_monitor import FileChangeMonitor
        self.last_json_monitor = FileChangeMonitor(os.path.join(emu_data_dir, "last.json"))

        # Repoint Settings at the emulator's config dir so changes persist across restarts.
        emu_cfg_dir = os.path.join(emu_data_dir, "config")
        os.makedirs(emu_cfg_dir, exist_ok=True)
        self.settings = Settings.Settings(data_dir=emu_cfg_dir)

        self.root_uri = "http://127.0.0.1:18181/"
        self.wifi_manager = StubWifiManager(on_status_change=self._on_wifi_status_change)
        self.wifi_manager.poll()

        # Replace the :80 bridge created by super().__init__() with the emulator port
        self.ws_bridge.stop()
        self.ws_bridge = AsyncWebSocketBridge(
            ws_url='ws://127.0.0.1:18181/websocket',
            backpressure_threshold=8192
        )
        self.ws_bridge.start()

        self._window = None

    def set_window(self, window):
        self._window = window

    def pedalboard_change(self, pedalboard=None):
        if pedalboard is None and self.pedalboard_list:
            pedalboard = self.pedalboard_list[0]
        if pedalboard is None:
            return
        super().pedalboard_change(pedalboard)
        pb = self.reload_pedalboard(pedalboard.bundle)
        self.set_current_pedalboard(pb)

    # -------------------------------------------------------------------------
    # Skip Pi-only system calls
    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------
    # Window integration — drain events every tick for input responsiveness,
    # but couple LCD flush + window repaint to poll_lcd_updates so the
    # emulator refresh rate matches the main loop's gating (200 ms on the
    # device) instead of running at ~100 fps.
    # -------------------------------------------------------------------------

    def poll_controls(self):
        if self._window is not None:
            self._window.process_events()
        super().poll_controls()

    def poll_lcd_updates(self):
        super().poll_lcd_updates()
        if self._window is not None:
            self._window.render()
