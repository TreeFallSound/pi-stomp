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

Overrides the handful of methods that hard-exit or crash when MOD is absent,
and redirects file paths away from /home/pistomp so the emulator can run
anywhere.
"""

import json
import logging
import os

import modalapi.pedalboard as Pedalboard
import pistomp.settings as Settings_module
from modalapi.modhandler import Modhandler
import common.token as Token


class EmulatorModhandler(Modhandler):

    def __init__(self, audiocard, homedir):
        # Redirect the settings file to a local directory so we never need
        # /home/pistomp/data/config to exist on the dev machine.
        emu_cfg_dir = os.path.join(os.path.expanduser("~"),
                                   ".pistomp_emulator", "config")
        os.makedirs(emu_cfg_dir, exist_ok=True)
        Settings_module.DATA_DIR = emu_cfg_dir

        super().__init__(audiocard, homedir)

        # Override paths that reference the Pi's filesystem
        emu_data_dir = os.path.join(os.path.expanduser("~"), ".pistomp_emulator")
        self.data_dir = emu_data_dir
        self.banks_file = os.path.join(emu_data_dir, "banks.json")
        self.pedalboard_modification_file = os.path.join(emu_data_dir, "last.json")
        self.pedalboard_change_timestamp = 0
        self.banks_file_timestamp = 0

        self._window = None   # set by the caller after window is created

    # -------------------------------------------------------------------------
    # Graceful MOD-host absence
    # -------------------------------------------------------------------------

    def load_pedalboards(self):
        resp = self._rest_get(self.root_uri + "pedalboard/list")
        if resp is None or resp.status_code != 200:
            logging.warning("mod-host not reachable — starting with empty pedalboard list")
            return

        pbs = json.loads(resp.text)
        for pb in pbs:
            logging.info("Loading pedalboard info: %s" % pb[Token.TITLE])
            bundle = pb[Token.BUNDLE]
            title = pb[Token.TITLE]
            pedalboard = Pedalboard.Pedalboard(title, bundle)
            pedalboard.load_bundle(bundle, self.plugin_dict)
            self.pedalboards[bundle] = pedalboard
            self.pedalboard_list.append(pedalboard)

    def pedalboard_change(self, pedalboard=None):
        if not self.pedalboard_list:
            logging.info("No pedalboards — initialising empty UI state")
            empty_pb = _EmptyPedalboard()
            if self.current is not None:
                del self.current
            self.current = self.Current(empty_pb)
            self.hardware.reinit(None)
            self.bind_current_pedalboard()
            self.lcd.link_data([], self.current, self.hardware.footswitches)
            self.lcd.draw_main_panel()
            return
        super().pedalboard_change(pedalboard)

    # -------------------------------------------------------------------------
    # Skip Pi-only system calls
    # -------------------------------------------------------------------------

    def poll_wifi(self):
        pass

    def system_info_load(self):
        pass

    # -------------------------------------------------------------------------
    # Window integration (pygame event processing + rendering)
    # -------------------------------------------------------------------------

    def poll_controls(self):
        if self._window is not None:
            self._window.process_events()
        super().poll_controls()

    def poll_lcd_updates(self):
        super().poll_lcd_updates()
        if self._window is not None:
            self._window.render()


class _EmptyPedalboard:
    """Minimal pedalboard stub used when MOD is not running."""
    def __init__(self):
        self.title = "(no pedalboards)"
        self.bundle = "/dev/null"
        self.plugins = []
