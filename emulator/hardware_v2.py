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

"""EmulatorHardwareV2 — software-only Hardware subclass for the v2 emulator.

Matches pi-Stomp Core (Pistompcore): one nav encoder with press, three
footswitches, one pot, one expression pedal, no relay interaction.
"""

import common.token as Token
from emulator.hardware_base import EmulatorHardwareBase
from emulator.controls import MockEncoder


class EmulatorHardwareV2(EmulatorHardwareBase):

    VERSION_LABEL = "v2"
    lcd_flip = True

    def __init__(self, cfg, handler, midiout, refresh_callback):
        super().__init__(cfg, handler, midiout, refresh_callback)

        self.init_lcd()
        self.init_encoders()
        self.init_footswitches()
        self.init_analog_controls()

    def init_encoders(self):
        nav = MockEncoder(type=Token.NAV, id=0)
        self.encoders.append(nav)
        self.nav_encoder = nav
        # tweak_encoders and volume_encoder stay None/[] — v2 has no extras

    def add_encoder(self, id, type, callback, longpress_callback, midi_channel, midi_cc):
        pass  # v2 has no config-driven encoders
