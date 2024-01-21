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
import RPi.GPIO as GPIO

import pistomp.analogswitch as AnalogSwitch
import pistomp.analogVU as AnalogVU
import common.token as Token
import common.util as Util
import pistomp.encoder as Encoder
import pistomp.encodermidicontrol as EncoderMidiControl
import pistomp.gpioswitch as gpioswitch
import pistomp.hardware as hardware
import pistomp.ledstrip as Ledstrip

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

# Encoder Pins
NAV_PIN_D = 17
NAV_PIN_CLK = 4
ENC = {1: {'D': 12, 'CLK': 25, 'SW': 16},
       2: {'D': 24, 'CLK': 23, 'SW': 26},
       3: {'D': 22, 'CLK': 27, 'SW': None}}

# ADC channels
NAV_ADC_CHAN = 0  #  3.0.p1
#NAV_ADC_CHAN = 4  # 3.0.rc1
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

        try:
            self.ledstrip = Ledstrip.Ledstrip()
        except Exception as e:
            self.ledstrip = None
            logging.error("Could not initialize LED Strip")

        self.init_spi()

        self.init_lcd()

        self.init_encoders()

        self.init_footswitches()

        self.init_analog_controls()

        self.init_vu()

        #self.reinit(None)  # TODO do we still need this?  Maybe after pb load?  mappings?

    def init_lcd(self):
        self.handler.add_lcd(Lcd.Lcd(self.handler.homedir, self.handler, flip=False))

    def add_encoder(self, id, type, callback, longpress_callback, midi_channel, midi_cc):
        enc_pins = Util.DICT_GET(ENC, id)
        if enc_pins is None:
            logging.error("Cannot create encoder object for id:", id)
            return

        # map the id to the actual pins
        d_pin = Util.DICT_GET(enc_pins, 'D')
        clk_pin = Util.DICT_GET(enc_pins, 'CLK')
        sw_pin = Util.DICT_GET(enc_pins, 'SW')

        if type == Token.VOLUME:
            enc = Encoder.Encoder(d_pin, clk_pin, callback=self.handler.system_menu_headphone_volume,
                                  type=type, id=id)
        else:
            enc = EncoderMidiControl.EncoderMidiControl(self.handler, d_pin=d_pin, clk_pin=clk_pin,
                                                        callback=callback,
                                                        midi_channel=midi_channel, midi_CC=midi_cc,
                                                        midiout=self.midiout, type=Token.KNOB, id=id)

        if sw_pin is not None:
            longpress = self.handler.get_callback(longpress_callback)
            enc_sw = gpioswitch.GpioSwitch(sw_pin, None, None, callback=self.handler.universal_encoder_sw,
                                           longpress_callback=longpress)
            self.encoder_switches.append(enc_sw)

        return enc

    def init_encoders(self):
        enc = Encoder.Encoder(NAV_PIN_D, NAV_PIN_CLK, callback=self.handler.universal_encoder_select)
        self.encoders.append(enc)
        # Nav encoder switch is a special case which gets initialized in init_analog_controls

        # Tweak encoders
        cfg = self.default_cfg.copy()
        self.create_encoders(cfg)

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
        if self.ledstrip is None:
            return

        # input gain setting on audio card is used to bias the VU meter thresholds
        input_gain = self.handler.audiocard.get_volume_parameter(self.handler.audiocard.CAPTURE_VOLUME)
        adc_baseline = self.handler.settings.get_setting('analogVU.adc_baseline')
        if adc_baseline is None:
            adc_baseline = 512
        indicator = AnalogVU.AnalogVU(self.spi, CLIP_L, 4, self.ledstrip, 5, input_gain, adc_baseline)
        self.indicators.append(indicator)
        indicator = AnalogVU.AnalogVU(self.spi, CLIP_R, 4, self.ledstrip, 4, input_gain, adc_baseline)
        self.indicators.append(indicator)

    def cleanup(self):
        if self.ledstrip is not None:
            self.ledstrip.cleanup()

    def test(self):
        pass
