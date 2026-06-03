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

"""EmulatorHardwareV3 — software-only Hardware subclass for the v3 emulator.

Matches pi-Stomp Tre (Pistomptre): one nav encoder, two tweak encoders,
one volume encoder, four footswitches, expression pedal.
"""

import common.token as Token

from emulator.hardware_base import EmulatorHardwareBase
from emulator.controls import MockEncoder, MockEncoderMidi


class EmulatorHardwareV3(EmulatorHardwareBase):

    VERSION_LABEL = "v3"
    lcd_flip = False

    def __init__(self, cfg, handler, midiout, refresh_callback):
        super().__init__(cfg, handler, midiout, refresh_callback)

        self.init_lcd()
        self.init_encoders()
        self.init_footswitches()
        self.init_analog_controls()

    def init_encoders(self):
        nav = MockEncoder(callback=self.handler.universal_encoder_select, id=0)
        nav.press_callback = self.handler.universal_encoder_sw
        self.encoders.append(nav)
        self.nav_encoder = nav

        cfg = self.default_cfg.copy()
        self.create_encoders(cfg)

    def add_encoder(self, id, type, callback, longpress_callback, midi_channel, midi_cc):
        """Called by Hardware.create_encoders() for each encoder in config."""
        if type == Token.VOLUME:
            enc = MockEncoder(
                callback=self.handler.system_menu_headphone_volume,
                type=type, id=id)
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

        if longpress_callback:
            lp = self.handler.get_callback(longpress_callback)
            if lp and isinstance(enc, MockEncoderMidi):
                enc.press_callback = lp

        return enc
