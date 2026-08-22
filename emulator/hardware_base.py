# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Shared base for all emulator Hardware subclasses.

Provides init_lcd, init_footswitches, init_analog_controls, init_relays,
cleanup, and test.  Subclasses only need to implement init_encoders (and
optionally add_encoder for config-driven encoder creation).
"""

import pistomp.hardware as hardware

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

        self.lcd_pygame = LcdPygame(320, 240, spi_hz=50_000_000)
        self.handler.add_lcd(
            Lcd.Lcd(self.handler.homedir, self.handler, flip=self.lcd_flip, display=self.lcd_pygame, spi_speed_hz=50_000_000)
        )

    def init_footswitches(self):
        for b in self.config.footswitches:
            if b.disable:
                continue
            fs = MockFootswitch(b.id, b.midi_CC, b.midi_channel, self.refresh_callback)
            self.footswitches.append(fs)
            self.register_controller(fs)

    def init_analog_controls(self):
        for b in self.config.analog_controls:
            if b.disable or b.midi_CC is None:
                continue
            ctrl = MockAnalogControl(b.midi_CC, b.midi_channel, b.type, b.id)
            self.analog_controls.append(ctrl)
            self.register_controller(ctrl)

    def init_relays(self):
        self.relay = StubRelay()

    def cleanup(self):
        from uilib.pygame_init import quit as pygame_quit

        pygame_quit()

    def test(self):
        pass
