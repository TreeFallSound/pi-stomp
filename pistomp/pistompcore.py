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

# This subclass defines hardware specific to pi-Stomp Core
# 3 Footswitches
# 1 Analog Pot
# 1 Expression Pedal
# 2 Encoders with switches
#
# A new version with different controls should have a new separate subclass

import RPi.GPIO as GPIO

import common.token as Token
import common.util as Util

import pistomp.analogmidicontrol as AnalogMidiControl
import pistomp.encoder as Encoder
import pistomp.encoderswitch as EncoderSwitch
import pistomp.footswitch as Footswitch
import pistomp.hardware as hardware
import pistomp.relay as Relay

import pistomp.lcd320x240 as Lcd
#import pistomp.lcd128x64 as Lcd
#import pistomp.lcd135x240 as Lcd
#import pistomp.lcdsy7789 as Lcd

# Pins (Unless the hardware has been changed, these should not be altered)
TOP_ENC_PIN_D = 17
TOP_ENC_PIN_CLK = 4
TOP_ENC_SWITCH_CHANNEL = 7
ENC_SW_THRESHOLD = 512

RELAY_RESET_PIN = 16
RELAY_SET_PIN = 12

# Map of Debounce chip pin (user friendly) to GPIO (code friendly)
DEBOUNCE_MAP = {0: 27, 1: 23, 2: 22, 3: 24, 4: 25}


class Pistompcore(hardware.Hardware):
    __single = None

    def __init__(self, cfg, mod, midiout, refresh_callback):
        super(Pistompcore, self).__init__(cfg, mod, midiout, refresh_callback)
        if Pistompcore.__single:
            raise Pistompcore.__single
        Pistompcore.__single = self

        self.mod = mod
        self.midiout = midiout
        self.debounce_map = DEBOUNCE_MAP

        GPIO.setmode(GPIO.BCM)

        self.init_spi()

        self.init_lcd()

        self.init_relays()

        self.init_encoders()

        self.init_footswitches()

        self.init_analog_controls()

        self.reinit(None)

    def init_lcd(self):
        self.mod.add_lcd(Lcd.Lcd(self.mod.homedir, self.mod))

    def init_encoders(self):
        top_enc = Encoder.Encoder(TOP_ENC_PIN_D, TOP_ENC_PIN_CLK, callback=self.mod.universal_encoder_select)
        self.encoders.append(top_enc)
        enc_sw = EncoderSwitch.EncoderSwitch(1, callback=self.mod.universal_encoder_sw)
        self.encoder_switches.append(enc_sw)

    def init_relays(self):
        self.relay = Relay.Relay(RELAY_SET_PIN, RELAY_RESET_PIN)

    def init_analog_controls(self):
        cfg = self.default_cfg.copy()
        if len(self.analog_controls) == 0:
            self.create_analog_controls(cfg)

    def init_footswitches(self):
        cfg = self.default_cfg.copy()
        if len(self.footswitches) == 0:
            self.create_footswitches(cfg)
