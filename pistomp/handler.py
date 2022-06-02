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


class Handler:

    def __init__(self):
        self.homedir = None
        self.lcd = None
        pass

    def noop(self):
        pass

    def update_lcd_fs(self, bypass_change=False):
        pass

    def add_lcd(self, lcd):
        pass

    def add_hardware(self, hardware):
        pass

    def poll_controls(self):
        pass

    def poll_modui_changes(self):
        pass

    def preset_incr_and_change(self):
        pass

    def preset_decr_and_change(self):
        pass

    def top_encoder_select(self, direction):
        pass

    def top_encoder_sw(self, value):
        pass

    def bot_encoder_select(self, direction):
        pass

    def bottom_encoder_sw(self, value):
        pass

    def universal_encoder_select(self, direction):
        pass

    def universal_encoder_sw(self, value):
        pass

    def cleanup(self):
        pass
