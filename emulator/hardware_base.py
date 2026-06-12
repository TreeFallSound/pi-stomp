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

"""Shared base for all emulator Hardware subclasses.

Provides init_lcd, init_footswitches, init_analog_controls, init_relays,
cleanup, and test.  Subclasses only need to implement init_encoders (and
optionally add_encoder for config-driven encoder creation).
"""

import pistomp.hardware as hardware
import common.token as Token
import common.util as Util

from emulator.controls import MockFootswitch, MockAnalogControl, MockEncoder
from emulator.lcd_pygame import LcdPygame
from emulator.stubs import StubRelay


class EmulatorHardwareBase(hardware.Hardware):

    VERSION_LABEL = ""
    lcd_flip = False

    def __init__(self, cfg, handler, midiout, refresh_callback):
        super().__init__(cfg, handler, midiout, refresh_callback)
        # spi stays None — no init_spi() call

        self.lcd_pygame: LcdPygame | None = None
        self.nav_encoder: MockEncoder | None = None
        self.tweak_encoders: list = []
        self.volume_encoder: MockEncoder | None = None

        # Ensure relay is always a stub so bypass footswitch config doesn't crash
        self.init_relays()

    # -------------------------------------------------------------------------
    # Shared init helpers
    # -------------------------------------------------------------------------

    def init_lcd(self):
        import pistomp.lcd320x240 as Lcd
        self.lcd_pygame = LcdPygame(320, 240)
        spi_speed = self.handler.settings.get_setting('lcd.spi_speed_mhz') or 24
        self.handler.add_lcd(Lcd.Lcd(self.handler.homedir, self.handler,
                                     flip=self.lcd_flip, display=self.lcd_pygame,
                                     spi_speed_mhz=spi_speed))

    def init_footswitches(self):
        cfg = self.default_cfg.copy()
        cfg_fs = cfg.get(Token.HARDWARE, {}).get(Token.FOOTSWITCHES)
        if not cfg_fs:
            return

        midi_channel = self.get_real_midi_channel(cfg)
        for f in cfg_fs:
            if Util.DICT_GET(f, Token.DISABLE):
                continue
            id_ = Util.DICT_GET(f, Token.ID)
            midi_cc = Util.DICT_GET(f, Token.MIDI_CC)
            fs = MockFootswitch(id_, midi_cc, midi_channel,
                                self.refresh_callback)
            self.footswitches.append(fs)
            if midi_cc is not None:
                key = "%d:%d" % (midi_channel, midi_cc)
                self.controllers[key] = fs

    def init_analog_controls(self):
        cfg = self.default_cfg.copy()
        hw_cfg = cfg.get(Token.HARDWARE, {}) if cfg else {}
        cfg_c = hw_cfg.get(Token.ANALOG_CONTROLLERS)
        if not cfg_c:
            return

        midi_channel = self.get_real_midi_channel(cfg)
        for c in cfg_c:
            if Util.DICT_GET(c, Token.DISABLE):
                continue
            id_ = Util.DICT_GET(c, Token.ID)
            midi_cc = Util.DICT_GET(c, Token.MIDI_CC)
            control_type = Util.DICT_GET(c, Token.TYPE)
            if midi_cc is None:
                continue
            ctrl = MockAnalogControl(midi_cc, midi_channel,
                                     control_type, id_, c)
            self.analog_controls.append(ctrl)
            key = "%d:%d" % (midi_channel, midi_cc)
            self.controllers[key] = ctrl

    def init_relays(self):
        self.relay = StubRelay()

    def cleanup(self):
        import pygame
        pygame.quit()

    def test(self):
        pass
