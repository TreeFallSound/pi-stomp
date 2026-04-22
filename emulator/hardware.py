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

"""EmulatorHardware - software-only Hardware subclass for the v3 emulator.

Replaces all GPIO / SPI / ADC interactions with mock controls and injects a
pygame-backed LCD driver.  No real hardware is touched.
"""

import logging

import common.token as Token
import common.util as Util
import pistomp.hardware as hardware

from emulator.controls import (MockEncoder, MockEncoderMidi,
                               MockFootswitch, MockAnalogControl)
from emulator.lcd_pygame import LcdPygame


class EmulatorHardware(hardware.Hardware):

    def __init__(self, cfg, handler, midiout, refresh_callback):
        super().__init__(cfg, handler, midiout, refresh_callback)
        # spi stays None — no init_spi() call

        self.lcd_pygame: LcdPygame | None = None
        self.nav_encoder: MockEncoder
        self.tweak_encoders: list[MockEncoderMidi] = []
        self.volume_encoder: MockEncoder

        self.init_lcd()
        self.init_encoders()
        self.init_footswitches()
        self.init_analog_controls()

    # -------------------------------------------------------------------------
    # Abstract method implementations
    # -------------------------------------------------------------------------

    def init_lcd(self):
        import pistomp.lcd320x240 as Lcd
        self.lcd_pygame = LcdPygame(320, 240)
        self.handler.add_lcd(Lcd.Lcd(self.handler.homedir, self.handler,
                                     flip=False, display=self.lcd_pygame))

    def init_encoders(self):
        # Nav encoder — no MIDI CC, drives universal_encoder_select
        nav = MockEncoder(callback=self.handler.universal_encoder_select, id=0)
        nav.press_callback = self.handler.universal_encoder_sw
        self.encoders.append(nav)
        self.nav_encoder = nav

        # Tweak / volume encoders from config
        cfg = self.default_cfg.copy()
        self.create_encoders(cfg)

    def add_encoder(self, id, type, callback, longpress_callback,
                    midi_channel, midi_cc):
        """Called by Hardware.create_encoders() for each encoder in config."""
        if type == Token.VOLUME:
            enc = MockEncoder(
                callback=self.handler.system_menu_headphone_volume,
                type=type, id=id)
            # volume encoder has no press on the real hardware
            self.volume_encoder = enc
        else:
            enc = MockEncoderMidi(
                handler=self.handler,
                callback=callback,
                midi_channel=midi_channel,
                midi_CC=midi_cc,
                midiout=self.midiout,
                type=Token.KNOB,
                id=id)
            enc.press_callback = self.handler.universal_encoder_sw
            self.tweak_encoders.append(enc)

        # Wire longpress (same callback as press for simplicity)
        if longpress_callback:
            lp = self.handler.get_callback(longpress_callback)
            if lp and isinstance(enc, MockEncoderMidi):
                enc.press_callback = lp

        return enc

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
                                self.midiout, self.refresh_callback)
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
            ctrl = MockAnalogControl(midi_cc, midi_channel, self.midiout,
                                     control_type, id_, c)
            self.analog_controls.append(ctrl)
            key = "%d:%d" % (midi_channel, midi_cc)
            self.controllers[key] = ctrl

    def init_relays(self):
        pass

    def cleanup(self):
        import pygame
        pygame.quit()

    def test(self):
        pass
