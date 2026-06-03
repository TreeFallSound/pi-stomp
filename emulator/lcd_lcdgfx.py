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

"""Emulator LCD subclass for the v1 pi-Stomp (GFX HAT 128x64 display).

Extends pistomp.lcdgfx.Lcd with the emulator-specific methods that
modhandler calls (link_data, draw_main_panel, update_footswitch, etc.).
All rendering logic lives in the parent class via injected GfxHat adapters.
"""

import pistomp.lcdgfx as lcdgfx
from emulator.gfxhat_adapters import GfxLcd, GfxBacklight, GfxTouch


class Lcd(lcdgfx.Lcd):

    def __init__(self, cwd, lcd_pygame):
        super().__init__(
            cwd,
            lcd=GfxLcd(lcd_pygame),
            backlight=GfxBacklight(),
            touch=GfxTouch(),
        )
        self._current = None
        self._footswitches = []

    def enc_step(self, direction):
        pass

    def enc_sw(self, value):
        pass

    def link_data(self, pedalboards, current, footswitches):
        self._current = current
        self._footswitches = footswitches

    def draw_main_panel(self):
        if self._current is None:
            return
        pb = self._current.pedalboard
        presets = self._current.presets
        preset_name = presets.get(self._current.preset_index) if presets else None
        self.draw_title(pb.title if hasattr(pb, 'title') else str(pb), preset_name, False, False)
        self.draw_analog_assignments(self._current.analog_controllers)
        self.draw_plugins(pb.plugins)
        self.draw_bound_plugins(pb.plugins, self._footswitches)

    def update_footswitch(self, footswitch):
        if self._current is not None:
            self.erase_zone(7)
            self.draw_bound_plugins(self._current.pedalboard.plugins, self._footswitches)

    def update_footswitches(self):
        if self._current is not None:
            self.erase_zone(7)
            self.draw_bound_plugins(self._current.pedalboard.plugins, self._footswitches)
