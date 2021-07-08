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

import pistomp.analogmidicontrol as AnalogMidiControl
import pistomp.encoder as Encoder
import pistomp.encoderswitch as EncoderSwitch
import pistomp.footswitch as Footswitch
import pistomp.hardware as hardware
import pistomp.relay as Relay

import pistomp.lcdili9341 as Lcd
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

# Each footswitch defined by a quad touple:
# 1: id (left = 0, mid = 1, right = 2)
# 2: the GPIO pin it's attached to
# 3: the associated LED output pin and
# 4: the MIDI Control (CC) message that will be sent when the switch is toggled
# Pin modifications should only be made if the hardware is changed accordingly
# 0=27, 1=23, 2=22, 3=24, 4=25
FOOTSW = [(0, 22, 0, 61), (1, 24, 13, 62), (2, 25, 26, 63)]

# TODO replace in default_config.yml
# Analog Controls defined by a triple touple:
# 1: the ADC channel
# 2: the minimum threshold for considering the value to be changed
# 3: the MIDI Control (CC) message that will be sent
# 4: control type (KNOB, EXPRESSION, etc.)
# Tweak, Expression Pedal
#ANALOG_CONTROL = [(0, 16, 60, 'KNOB1'), (6, 16, 66, 'KNOB2'), (5, 16, 65, 'KNOB3'), (4, 16, 64, 'KNOB4')]
ANALOG_CONTROL = []

class Pistompcore(hardware.Hardware):
    __single = None

    def __init__(self, cfg, mod, midiout, refresh_callback):
        super(Pistompcore, self).__init__(cfg, mod, midiout, refresh_callback)
        if Pistompcore.__single:
            raise Pistompcore.__single
        Pistompcore.__single = self

        self.mod = mod
        self.midiout = midiout

        GPIO.setmode(GPIO.BCM)

        self.init_spi()

        self.init_lcd()

        self.init_relays()

        self.init_footswitches()

        self.init_analog_controls()

        self.init_encoders()

    def init_lcd(self):
        self.mod.add_lcd(Lcd.Lcd(self.mod.homedir))

    def init_analog_controls(self):
        for c in ANALOG_CONTROL:
            control = AnalogMidiControl.AnalogMidiControl(self.spi, c[0], c[1], c[2], self.midi_channel,
                                                          self.midiout, c[3])
            self.analog_controls.append(control)
            key = format("%d:%d" % (self.midi_channel, c[2]))
            self.controllers[key] = control  # Controller.Controller(self.midi_channel, c[1], Controller.Type.ANALOG)

    def init_encoders(self):
        top_enc = Encoder.Encoder(TOP_ENC_PIN_D, TOP_ENC_PIN_CLK, callback=self.mod.universal_encoder_select)
        self.encoders.append(top_enc)
        EncoderSwitch.EncoderSwitch(1, callback=self.mod.universal_encoder_sw)

    def init_footswitches(self):
        for f in FOOTSW:
            fs = Footswitch.Footswitch(f[0], f[1], f[2], f[3], self.midi_channel, self.midiout,
                                       refresh_callback=self.refresh_callback)
            self.footswitches.append(fs)
        self.reinit(None)

    def init_relays(self):
        self.relay = Relay.Relay(RELAY_SET_PIN, RELAY_RESET_PIN)
