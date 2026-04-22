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

"""EmulatorModhandler — Modhandler subclass for local development.

Requires MOD Desktop to be running locally (http://127.0.0.1:18181).
Overrides Pi-only system calls and wires pygame rendering into the poll loop.
"""

import logging
import os

import pistomp.settings as Settings_module
from modalapi.modhandler import Modhandler


class EmulatorModhandler(Modhandler):

    def __init__(self, homedir):
        emu_cfg_dir = os.path.join(os.path.expanduser("~"), ".pistomp_emulator", "config")
        os.makedirs(emu_cfg_dir, exist_ok=True)
        Settings_module.DATA_DIR = emu_cfg_dir

        super().__init__(_VirtualAudiocard(), homedir)

        emu_data_dir = os.path.join(os.path.expanduser("~"), ".pistomp_emulator")
        self.data_dir = emu_data_dir
        self.banks_file = os.path.join(emu_data_dir, "banks.json")
        self.pedalboard_modification_file = os.path.join(emu_data_dir, "last.json")
        self.pedalboard_change_timestamp = 0
        self.banks_file_timestamp = 0

        self.root_uri = "http://127.0.0.1:18181/"
        self.wifi_manager = _StubWifiManager()

        self._window = None   # set by the caller after window is created

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
    # Window integration — render on every poll_controls tick (~100 fps)
    # instead of waiting for the gated poll_lcd_updates (every 200 ms).
    # -------------------------------------------------------------------------

    def poll_controls(self):
        if self._window is not None:
            self._window.process_events()
        super().poll_controls()
        if self._lcd is not None:
            self._lcd.poll_updates()
        if self._window is not None:
            self._window.render()

    def poll_lcd_updates(self):
        pass  # handled in poll_controls


class _VirtualAudiocard:
    """Stub audiocard that holds state in memory; no hardware access."""

    CAPTURE_VOLUME = "capture_volume"
    MASTER         = "master_volume"
    DAC_EQ         = "dac_eq"
    EQ_1           = "eq1"
    EQ_2           = "eq2"
    EQ_3           = "eq3"
    EQ_4           = "eq4"
    EQ_5           = "eq5"

    def __init__(self):
        self._volumes  = {}
        self._switches = {}
        self._bypass_left  = False
        self._bypass_right = False

    def get_volume_parameter(self, symbol):
        return self._volumes.get(symbol, 0.0)

    def set_volume_parameter(self, symbol, value):
        self._volumes[symbol] = value

    def get_switch_parameter(self, symbol):
        return self._switches.get(symbol, False)

    def set_switch_parameter(self, symbol, value):
        self._switches[symbol] = value
        return True

    def get_bypass_left(self):
        return self._bypass_left

    def set_bypass_left(self, value):
        self._bypass_left = value

    def get_bypass_right(self):
        return self._bypass_right

    def set_bypass_right(self, value):
        self._bypass_right = value


class _StubWifiManager:
    def poll(self):
        return None

    def get_ssid(self):
        return None

    def get_psk(self):
        return None

    def enable_hotspot(self):
        pass

    def disable_hotspot(self):
        pass

    def configure_wifi(self, ssid, password):
        return None
