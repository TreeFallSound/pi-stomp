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

"""EmulatorHardwareV1 — software-only Hardware subclass for the v1 emulator.

Matches the original pi-Stomp (Pistomp): two encoders with press (top for
pedalboard/preset nav, bottom for effect nav), three footswitches, no
config-driven analog controls.
"""

import common.token as Token
from emulator.hardware_base import EmulatorHardwareBase
from emulator.controls import MockEncoder
from emulator.lcd_pygame import LcdPygame
from emulator.lcd_lcdgfx import Lcd as LcdGfx


class EmulatorHardwareV1(EmulatorHardwareBase):

    VERSION_LABEL = "v1"
    lcd_flip = False

    def __init__(self, cfg, handler, midiout, refresh_callback):
        super().__init__(cfg, handler, midiout, refresh_callback)

        self.init_lcd()
        self.init_encoders()
        self.init_footswitches()
        self.init_analog_controls()

    def init_lcd(self):
        self.lcd_pygame = LcdPygame(128, 64)
        self.handler.add_lcd(LcdGfx(self.handler.homedir, self.lcd_pygame))

    def init_encoders(self):
        top = MockEncoder(type=Token.NAV, id=0)
        top.label = "Nav1 (pedalboard/preset)"
        self.encoders.append(top)
        self.nav_encoder = top

        bot = MockEncoder(type=Token.NAV, id=1)
        bot.label = "Nav2 (plugin/value)"
        self.encoders.append(bot)
        self.tweak_encoders.append(bot)

    def add_encoder(self, id, type, callback, longpress_callback, midi_channel, midi_cc):
        pass  # v1 has no config-driven encoders
