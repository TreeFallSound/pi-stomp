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

import logging
import os
import spidev

import common.token as Token
import pistomp.analogmidicontrol

from abc import abstractmethod


class Hardware:

    def __init__(self, default_config, mod, midiout, refresh_callback):
        logging.info("Init hardware: " + type(self).__name__)
        self.mod = mod
        self.midiout = midiout
        self.refresh_callback = refresh_callback
        self.spi = None
        self.test_pass = False
        self.test_sentinel = None

        # From config file(s)
        self.default_cfg = default_config
        self.version = self.default_cfg[Token.HARDWARE][Token.VERSION]
        self.cfg = None          # compound cfg (default with user/pedalboard specific cfg overlaid)
        self.midi_channel = 0

        # Standard hardware objects (not required to exist)
        self.relay = None
        self.analog_controls = []
        self.encoders = []
        self.controllers = {}
        self.footswitches = []

    def init_spi(self):
        self.spi = spidev.SpiDev()
        self.spi.open(0, 1)  # Bus 0, CE1
        #self.spi.max_speed_hz = 24000000  # TODO match with LCD or don't specify
        self.spi.max_speed_hz = 1000000

    def poll_controls(self):
        # This is intended to be called periodically from main working loop to poll the instantiated controls
        for c in self.analog_controls:
            c.refresh()
        for e in self.encoders:
            e.read_rotary()

    def reinit(self, cfg):
        # reinit hardware as specified by the new cfg context (after pedalboard change, etc.)
        self.cfg = self.default_cfg.copy()

        self.__init_midi_default()
        self.__init_footswitches_default()
        if cfg is not None:
            self.__init_midi(cfg)
            self.__init_footswitches(cfg)

    @abstractmethod
    def init_analog_controls(self):
        pass

    @abstractmethod
    def init_encoders(self):
        pass

    @abstractmethod
    def init_footswitches(self):
        pass

    @abstractmethod
    def init_relays(self):
        pass

    @abstractmethod
    def test(self):
        pass

    def run_test(self):
        # if test sentinel file exists execute hardware test
        script_dir = os.path.dirname(os.path.realpath(__file__))
        self.test_sentinel = os.path.join(script_dir, ".hardware_tests_passed")
        if not os.path.isfile(self.test_sentinel):
            self.test_pass = False
            self.test()

    def __init_midi_default(self):
        self.__init_midi(self.cfg)

    def __init_midi(self, cfg):
        try:
            val = cfg[Token.HARDWARE][Token.MIDI][Token.CHANNEL]
            # LAME bug in Mod detects MIDI channel as one higher than sent (7 sent, seen by mod as 8) so compensate here
            self.midi_channel = val - 1 if val > 0 else 0
        except KeyError:
            pass
        # TODO could iterate thru all objects here instead of handling in __init_footswitches
        for ac in self.analog_controls:
            if isinstance(ac, pistomp.analogmidicontrol.AnalogMidiControl):
                ac.set_midi_channel(self.midi_channel)

    def __init_footswitches_default(self):
        for fs in self.footswitches:
            fs.clear_relays()
        self.__init_footswitches(self.cfg)

    def __init_footswitches(self, cfg):
        if cfg is None or (Token.HARDWARE not in cfg) or (Token.FOOTSWITCHES not in cfg[Token.HARDWARE]):
            return
        cfg_fs = cfg[Token.HARDWARE][Token.FOOTSWITCHES]
        idx = 0
        for fs in self.footswitches:
            # See if a corresponding cfg entry exists.  if so, override
            f = None
            for f in cfg_fs:
                if f[Token.ID] == idx:
                    break
                else:
                    f = None

            if f is not None:
                fs.clear_display_label()

                # Bypass
                fs.clear_relays()
                if Token.BYPASS in f:
                    # TODO no more right or left
                    if f[Token.BYPASS] == Token.LEFT_RIGHT or f[Token.BYPASS] == Token.LEFT:
                        fs.add_relay(self.relay)
                        fs.set_display_label("byps")

                # Midi
                if Token.MIDI_CC in f:
                    cc = f[Token.MIDI_CC]
                    if cc == Token.NONE:
                        fs.set_midi_CC(None)
                        for k, v in self.controllers.items():
                            if v == fs:
                                self.controllers.pop(k)
                                break
                    else:
                        fs.set_midi_channel(self.midi_channel)
                        fs.set_midi_CC(cc)
                        key = format("%d:%d" % (self.midi_channel, fs.midi_CC))
                        self.controllers[key] = fs   # TODO problem if this creates a new element?

                # Preset Control
                fs.clear_preset()
                if Token.PRESET in f:
                    preset_value = f[Token.PRESET]
                    if preset_value == Token.UP:
                        fs.add_preset(callback=self.mod.preset_incr_and_change)
                        fs.set_display_label("Pre++")
                    if preset_value == Token.DOWN:
                        fs.add_preset(callback=self.mod.preset_decr_and_change)
                        fs.set_display_label("Down")
            idx += 1
