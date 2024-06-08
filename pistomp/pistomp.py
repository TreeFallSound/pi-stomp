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

# This subclass defines hardware specific to pi-stomp! v1
# 3 Footswitches
# 1 Analog Pot
# 1 Expression Pedal
# 2 Encoders with switches
#
# A new version with different controls should have a new separate subclass

import gpiozero as GPIO

from pathlib import Path
import common.token as Token
import common.util as Util
import pistomp.analogmidicontrol as AnalogMidiControl
import pistomp.analogswitch as AnalogSwitch
import pistomp.encoder as Encoder
import pistomp.footswitch as Footswitch
import pistomp.hardware as hardware
import pistomp.relay as Relay

import pistomp.lcdgfx as Lcd

import sys
import time

# Pins (Unless the hardware has been changed, these should not be altered)
TOP_ENC_PIN_D = 17
TOP_ENC_PIN_CLK = 4
TOP_ENC_SWITCH_CHANNEL = 7
BOT_ENC_PIN_D = 22
BOT_ENC_PIN_CLK = 27
BOT_ENC_SWITCH_CHANNEL = 6
ENC_SW_THRESHOLD = 512

RELAY_RESET_PIN = 16
RELAY_SET_PIN = 12

# Each footswitch defined by a quad touple:
# 1: id (left = 0, mid = 1, right = 2)
# 2: the GPIO pin it's attached to
# 3: the associated LED output pin and
# 4: the MIDI Control (CC) message that will be sent when the switch is toggled
# Pin modifications should only be made if the hardware is changed accordingly
FOOTSW = [(0, 23, 24, 61), (1, 25, 0, 62), (2, 13, 26, 63)]

# TODO replace in default_config.yml
# Analog Controls defined by a triple touple:
# 1: the ADC channel
# 2: the minimum threshold for considering the value to be changed
# 3: the MIDI Control (CC) message that will be sent
# 4: control type (KNOB, EXPRESSION, etc.)
# Tweak, Expression Pedal
ANALOG_CONTROL = [(0, 16, 64, 'KNOB'), (1, 16, 65, 'EXPRESSION')]

class Pistomp(hardware.Hardware):
    __single = None

    def __init__(self, cfg, mod, midiout, refresh_callback):
        super(Pistomp, self).__init__(cfg, mod, midiout, refresh_callback)
        if Pistomp.__single:
            raise Pistomp.__single
        Pistomp.__single = self

        self.cfg = cfg
        self.mod = mod
        self.midiout = midiout

        self.init_spi()

        self.init_lcd()

        self.run_test()

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
        top_enc = Encoder.Encoder(TOP_ENC_PIN_D, TOP_ENC_PIN_CLK, callback=self.mod.top_encoder_select)
        self.encoders.append(top_enc)
        bot_enc = Encoder.Encoder(BOT_ENC_PIN_D, BOT_ENC_PIN_CLK, callback=self.mod.bot_encoder_select)
        self.encoders.append(bot_enc)
        control = AnalogSwitch.AnalogSwitch(self.spi, TOP_ENC_SWITCH_CHANNEL, ENC_SW_THRESHOLD,
                                            callback=self.mod.top_encoder_sw)
        self.analog_controls.append(control)
        control = AnalogSwitch.AnalogSwitch(self.spi, BOT_ENC_SWITCH_CHANNEL, ENC_SW_THRESHOLD,
                                            callback=self.mod.bottom_encoder_sw)
        self.analog_controls.append(control)

    def init_footswitches(self):
        cfg_fss = self.cfg[Token.HARDWARE][Token.FOOTSWITCHES]
        for f in FOOTSW:
            id = None
            tt = None
            # look for any special functions defined in config file (eg. tap_tempo)
            for cfg_fs in cfg_fss:
                id = Util.DICT_GET(cfg_fs, Token.ID)
            if id:
                tt = Util.DICT_GET(cfg_fs, Token.TAP_TEMPO)

            fs = Footswitch.Footswitch(f[0], f[2], None, f[3], self.midi_channel, self.midiout,
                                       refresh_callback=self.refresh_callback, gpio_input=f[1],
                                       tap_tempo_callback=self.handler.get_callback(tt))
            self.footswitches.append(fs)
        self.reinit(None)

    def init_relays(self):
        self.relay = Relay.Relay(RELAY_SET_PIN, RELAY_RESET_PIN)

    def cleanup(self):
        pass

    # Test procedure for verifying hardware controls
    def test(self):
        self.mod.lcd.erase_all()
        self.mod.lcd.draw_title("Hardware test...", None, False, False)
        failed = 0

        try:
            # TODO kinda lame that the instantiations of hardware objects here must match those in __init__
            # except with different callbacks

            # Footswitches
            for f in FOOTSW:
                self.mod.lcd.draw_info_message("Press Footswitch %d" % int(f[0] + 1))
                fs = Footswitch.Footswitch(f[0], f[2], None, f[3], self.midi_channel, self.midiout,
                                           refresh_callback=self.test_passed, gpio_input=f[1])
                self.test_pass = False
                timeout = 1000  # 10 seconds
                led = fs.led
                initial_value = led.is_lit
                while self.test_pass is False and timeout > 0:
                    fs.poll()
                    new_value = led.is_lit  # Verify that LED pin toggles
                    if new_value is not initial_value:
                        break
                    time.sleep(0.01)
                    timeout = timeout - 1
                del fs
                if timeout > 0:
                    self.mod.lcd.draw_info_message("Passed")
                else:
                    self.mod.lcd.draw_info_message("Failed")
                    failed = failed + 1
                time.sleep(1.2)

            # Encoder rotary
            encoders = [["Turn the PBoard Knob", TOP_ENC_PIN_D, TOP_ENC_PIN_CLK],
                        ["Turn the Effect Knob", BOT_ENC_PIN_D, BOT_ENC_PIN_CLK]]
            for e in encoders:
                enc = Encoder.Encoder(e[1], e[2], callback=self.test_passed)
                self.mod.lcd.draw_info_message(e[0])
                self.test_pass = False
                timeout = 1000
                while self.test_pass is False and timeout > 0:
                    enc.read_rotary()
                    time.sleep(0.01)
                    timeout = timeout - 1
                del enc
                if timeout > 0:
                    self.mod.lcd.draw_info_message("Passed")
                else:
                    self.mod.lcd.draw_info_message("Failed")
                    failed = failed + 1
                time.sleep(1.2)

            # Encoder switches
            encoders = [["Press the PBoard Knob", TOP_ENC_SWITCH_CHANNEL],
                        ["Press the Effect Knob", BOT_ENC_SWITCH_CHANNEL]]
            for e in encoders:
                enc = AnalogSwitch.AnalogSwitch(self.spi, e[1], ENC_SW_THRESHOLD, callback=self.test_passed)
                self.mod.lcd.draw_info_message(e[0])
                self.test_pass = False
                timeout = 1000
                while self.test_pass is False and timeout > 0:
                    enc.refresh()
                    time.sleep(0.01)
                    timeout = timeout - 1
                del enc
                if timeout > 0:
                    self.mod.lcd.draw_info_message("Passed")
                else:
                    self.mod.lcd.draw_info_message("Failed")
                    failed = failed + 1
                time.sleep(1.2)

            # Analog Knobs
            self.mod.lcd.draw_info_message("Turn the Tweak knob")
            c = ANALOG_CONTROL[0]
            control = AnalogMidiControl.AnalogMidiControl(self.spi, c[0], c[1], c[2], self.midi_channel,
                                                          self.midiout, c[3])
            self.test_pass = False
            timeout = 1000
            initial_value = control.readChannel()
            while self.test_pass is False and timeout > 0:
                time.sleep(0.01)
                pot_adjust = abs(control.readChannel() - initial_value)
                if pot_adjust > c[1]:
                    break
                timeout = timeout - 1
            del control
            if timeout > 0:
                self.mod.lcd.draw_info_message("Passed")
            else:
                self.mod.lcd.draw_info_message("Failed")
                failed = failed + 1
            time.sleep(1.2)

            if failed > 0:
                self.mod.lcd.draw_info_message("%d control(s) failed" % failed)
                time.sleep(3)
            else:
                # create sentinel file so test procedure is skipped next boot
                f = Path(self.test_sentinel)
                f.touch()
            self.mod.lcd.draw_info_message("Restarting...")
            time.sleep(1.2)

        except KeyboardInterrupt:
            return

        finally:
            self.mod.lcd.cleanup()
            sys.exit()

    def test_passed(self, data = None, footswitch = None):
        self.test_pass = True
