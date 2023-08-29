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

import RPi.GPIO as GPIO

import pistomp.analogswitch as AnalogSwitch
import pistomp.analogVU as AnalogVU
import pistomp.encoder as Encoder
import pistomp.encodermidicontrol as EncoderMidiControl
import pistomp.gpioswitch as gpioswitch
import pistomp.hardware as hardware

#import pistomp.lcdili9341 as Lcd   # pistompcore UI
import pistomp.lcd320x240 as Lcd   # Tre UI

# This subclass defines hardware specific to pi-Stomp Tre
# 4 Encoders (one for Navigation, 3 for tweaking)
# 3 Encoder switches (one for Navigation, 2 for tweak pots)
# 1 Expression Input
# 2 Clipping indicator LEDS
#
# Unless the hardware has been changed, Pin and ADC assignments should not be altered
#
# A new version with different controls should have a new separate subclass

# Pins
NAV_PIN_D = 17
NAV_PIN_CLK = 4
ENC1_PIN_D = 12
ENC1_PIN_CLK = 25
ENC1_PIN_SW = 16
ENC1_MIDI_CC = 70
ENC2_PIN_D = 24
ENC2_PIN_CLK = 23
ENC2_PIN_SW = 26
ENC2_MIDI_CC = 71
ENC3_PIN_D = 22
ENC3_PIN_CLK = 27

# ADC channels
# NAV_ADC_CHAN = 0  #  3.0.p1
# FOOTSWITCH0 = 1
# FOOTSWITCH1 = 2
# FOOTSWITCH2 = 3
# FOOTSWITCH3 = 4
FOOTSWITCH0 = 0  # 3.0.rc1
FOOTSWITCH1 = 1
FOOTSWITCH2 = 2
FOOTSWITCH3 = 3
NAV_ADC_CHAN = 4
EXPRESSION = 5
CLIP_L = 6
CLIP_R = 7

ENC_SW_THRESHOLD = 512  # assumes the value range of the ADC is 0 thru 1023 (10-bit ADC)


class Pistomptre(hardware.Hardware):
    __single = None

    def __init__(self, cfg, handler, midiout, refresh_callback):
        super(Pistomptre, self).__init__(cfg, handler, midiout, refresh_callback)
        if Pistomptre.__single:
            raise Pistomptre.__single
        Pistomptre.__single = self

        self.handler = handler
        self.midiout = midiout

        GPIO.setmode(GPIO.BCM)

        self.init_spi()

        self.init_lcd()

        self.init_encoders()

        self.init_footswitches()

        self.init_analog_controls()

        self.init_vu()

        #self.reinit(None)  # TODO do we still need this?  Maybe after pb load?  mappings?

    def init_lcd(self):
        self.handler.add_lcd(Lcd.Lcd(self.handler.homedir, self.handler, flip=False))

    def add_tweak_encoder(self, d_pin, clk_pin, sw_pin, callback, midi_channel, midi_CC):
        enc = EncoderMidiControl.EncoderMidiControl(self.handler, d_pin=d_pin, clk_pin=clk_pin, callback=callback,
                                                    use_interrupt=True, midi_channel=midi_channel, midi_CC=midi_CC,
                                                    midiout=self.midiout)
        self.encoders.append(enc)
        key = format("%d:%d" % (midi_channel, midi_CC))
        self.controllers[key] = enc

        # TODO add encoder switch action
        # if action is specified via config file could do something like this
        # action = {}
        # action["universal_encoder_sw"] = self.handler.universal_encoder_sw
        # enc_sw = gpioswitch.GpioSwitch(sw_pin, None, None, callback=action["universal_encoder_sw"])
        # self.encoder_switches.append(enc_sw)

    def init_encoders(self):
        enc = Encoder.Encoder(NAV_PIN_D, NAV_PIN_CLK, callback=self.handler.universal_encoder_select)
        self.encoders.append(enc)
        # Nav encoder switch is a special case which gets initialized in init_analog_controls

        # Tweak encoders
        cfg = self.default_cfg.copy()
        midi_channel = self.get_real_midi_channel(cfg)
        self.add_tweak_encoder(ENC1_PIN_D, ENC1_PIN_CLK, ENC1_PIN_SW, None, midi_channel, ENC1_MIDI_CC)
        self.add_tweak_encoder(ENC2_PIN_D, ENC2_PIN_CLK, ENC2_PIN_SW, None, midi_channel, ENC2_MIDI_CC)
        # TODO tweak3

    def init_relays(self):
        pass

    def init_analog_controls(self):
        # These are defined in the config file
        cfg = self.default_cfg.copy()
        if len(self.analog_controls) == 0:
            self.create_analog_controls(cfg)

        # Special case Navigation encoder switch
        control = AnalogSwitch.AnalogSwitch(self.spi, NAV_ADC_CHAN, ENC_SW_THRESHOLD,
                                            callback=self.handler.universal_encoder_sw)
        self.analog_controls.append(control)

    def init_footswitches(self):
        # These are defined in the config file
        cfg = self.default_cfg.copy()
        if len(self.footswitches) == 0:
            self.create_footswitches(cfg)

    def init_vu(self):
        indicator = AnalogVU.AnalogVU(self.spi, CLIP_L, 4, self.ledstrip, 5)  # TODO Make adc_chan and threshold configurable
        self.indicators.append(indicator)
        indicator = AnalogVU.AnalogVU(self.spi, CLIP_R, 4, self.ledstrip, 4)
        self.indicators.append(indicator)

    def test(self):
        pass
