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

"""Hardware and system stubs shared across all emulator versions.

VirtualAudiocard  — in-memory audiocard; no ALSA/hardware access.
StubWifiManager   — no-op wifi; satisfies Mod/Modhandler's wifi_manager.
StubRelay         — no-op relay; satisfies the Relay interface without GPIO.
"""


from pistomp.audiocard import Audiocard


class VirtualAudiocard(Audiocard):
    """In-memory audiocard stub; holds EQ/volume/bypass state."""

    CAPTURE_VOLUME = "capture_volume"
    MASTER         = "master_volume"
    DAC_EQ         = "dac_eq"
    EQ_1           = "eq1"
    EQ_2           = "eq2"
    EQ_3           = "eq3"
    EQ_4           = "eq4"
    EQ_5           = "eq5"

    def __init__(self):
        self._volumes      = {}
        self._switches     = {}
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

    def set_output_muted(self, muted: bool) -> None:
        pass


class StubWifiManager:
    """No-op wifi manager; satisfies the WifiManager interface."""

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


class StubRelay:
    """No-op relay; satisfies the Relay interface without GPIO."""

    def __init__(self):
        self.enabled = True

    def init_state(self):
        return self.enabled

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False

    def update(self, enable):
        self.enabled = enable

    def get(self):
        return self.enabled
