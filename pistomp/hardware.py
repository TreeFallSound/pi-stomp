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
import sys

import common.token as Token
import common.util as Util
import pistomp.analogmidicontrol as AnalogMidiControl
import pistomp.footswitch as Footswitch
import pistomp.ledstrip as Ledstrip

from abc import abstractmethod


class Hardware:

    def __init__(self, default_config, handler, midiout, refresh_callback):
        logging.info("Init hardware: " + type(self).__name__)
        self.handler = handler
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
        self.encoder_switches = []
        self.debounce_map = None
        self.ledstrip = None

    def init_spi(self):
        self.spi = spidev.SpiDev()
        self.spi.open(0, 1)  # Bus 0, CE1
        # TODO SPI bus is shared by ADC and LCD.  Ideally, they would use the same frequency.
        # MCP3008 ADC has a max of 1MHz (higher makes it loose resolution)
        # Color LCD needs to run at 24Mhz
        # until we can get them on the same, we'll set ADC (the one set here) to be a slower multiple of the LCD
        #self.spi.max_speed_hz = 24000000
        #self.spi.max_speed_hz =  1000000
        self.spi.max_speed_hz = 240000

    def poll_controls(self):
        # This is intended to be called periodically from main working loop to poll the instantiated controls
        for c in self.analog_controls:
            c.refresh()
        for e in self.encoders:
            e.read_rotary()
        for s in self.encoder_switches:
            s.poll()
        for s in self.footswitches:
            s.poll()

    def reinit(self, cfg):
        # reinit hardware as specified by the new cfg context (after pedalboard change, etc.)
        self.cfg = self.default_cfg.copy()

        self.__init_midi_default()
        self.__init_footswitches(self.cfg)

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

    def create_footswitches(self, cfg):
        if cfg is None or (Token.HARDWARE not in cfg) or (Token.FOOTSWITCHES not in cfg[Token.HARDWARE]):
            return

        cfg_fs = cfg[Token.HARDWARE][Token.FOOTSWITCHES]
        if cfg_fs is None:
            return

        # determine if an ledstrip is referenced, if so create an object
        ledstrip_gpio = None
        gpio_output_list = []
        for f in cfg_fs:
            if self.ledstrip is None and Util.DICT_GET(f, Token.LEDSTRIP_POSITION) is not None:
                self.ledstrip = Ledstrip.Ledstrip()
                ledstrip_gpio = self.ledstrip.get_gpio()
            gpio_output_list.append(Util.DICT_GET(f, Token.GPIO_OUTPUT))

        # Must make sure a gpio_output is not specified on the PWM pin used for an ledstring
        if ledstrip_gpio is not None and ledstrip_gpio in gpio_output_list:
            logging.error("Config file error.  Cannot have %s on the same GPIO as used for an ledstring referenced by %s"
                          % (Token.GPIO_OUTPUT, Token.LEDSTRIP_POSITION))
            sys.exit()

        midi_channel = self.get_real_midi_channel(cfg)
        idx = 0
        for f in cfg_fs:
            if Util.DICT_GET(f, Token.DISABLE) is True:
                continue

            di = Util.DICT_GET(f, Token.DEBOUNCE_INPUT)
            if self.debounce_map and di in self.debounce_map:
                gpio_input = self.debounce_map[di]
            else:
                gpio_input = Util.DICT_GET(f, Token.GPIO_INPUT)

            adc_input = Util.DICT_GET(f, Token.ADC_INPUT)
            gpio_output = Util.DICT_GET(f, Token.GPIO_OUTPUT)
            tap_tempo_callback = Util.DICT_GET(f, Token.TAP_TEMPO)
            midi_cc = Util.DICT_GET(f, Token.MIDI_CC)
            id = Util.DICT_GET(f, Token.ID)
            led_position = Util.DICT_GET(f, Token.LEDSTRIP_POSITION)

            pixel = None
            if self.ledstrip and led_position is not None:
                pixel = self.ledstrip.add_pixel(id if id else idx, led_position)

            # Create the footswitch object
            if adc_input is None and gpio_input is None:
                 logging.error("Config file error.  Footswitch specified without %s or %s or %s" %
                               (Token.DEBOUNCE_INPUT, Token.GPIO_INPUT, Token.ADC_INPUT))
                 continue
            if adc_input is not None:
                fs = Footswitch.Footswitch(id if id else idx, gpio_output, pixel, midi_cc, midi_channel,
                                           self.midiout, refresh_callback=self.refresh_callback,
                                           adc_input=adc_input, spi=self.spi,
                                           tap_tempo_callback=self.handler.get_callback(tap_tempo_callback))
                logging.debug("Created Footswitch on ADC input: %d, Midi Chan: %d, CC: %s" %
                              (adc_input, midi_channel, midi_cc))
            elif gpio_input is not None:
                fs = Footswitch.Footswitch(id if id else idx, gpio_output, pixel, midi_cc, midi_channel,
                                           self.midiout, refresh_callback=self.refresh_callback,
                                           gpio_input=gpio_input,
                                           tap_tempo_callback=self.handler.get_callback(tap_tempo_callback))
                logging.debug("Created Footswitch on GPIO input: %d, Midi Chan: %d, CC: %s" %
                              (gpio_input, midi_channel, midi_cc))

            self.footswitches.append(fs)
            idx += 1

    def create_analog_controls(self, cfg):
        if cfg is None or (Token.HARDWARE not in cfg) or (Token.ANALOG_CONTROLLERS not in cfg[Token.HARDWARE]):
            return

        midi_channel = self.get_real_midi_channel(cfg)
        cfg_c = cfg[Token.HARDWARE][Token.ANALOG_CONTROLLERS]
        if cfg_c is None:
            return
        for c in cfg_c:
            if Util.DICT_GET(c, Token.DISABLE) is True:
                continue

            adc_input = Util.DICT_GET(c, Token.ADC_INPUT)
            midi_cc = Util.DICT_GET(c, Token.MIDI_CC)
            threshold = Util.DICT_GET(c, Token.THRESHOLD)
            control_type = Util.DICT_GET(c, Token.TYPE)

            if adc_input is None:
                logging.error("Config file error.  Analog control specified without %s" % Token.ADC_INPUT)
                continue
            if midi_cc is None:
                logging.error("Config file error.  Analog control specified without %s" % Token.MIDI_CC)
                continue
            if threshold is None:
                threshold = 16  # Default, 1024 is full scale

            control = AnalogMidiControl.AnalogMidiControl(self.spi, adc_input, threshold, midi_cc, midi_channel,
                                                          self.midiout, control_type, c)
            self.analog_controls.append(control)
            key = format("%d:%d" % (midi_channel, midi_cc))
            self.controllers[key] = control
            logging.debug("Created AnalogMidiControl Input: %d, Midi Chan: %d, CC: %d" %
                          (adc_input, midi_channel, midi_cc))

    def get_real_midi_channel(self, cfg):
        chan = 0
        try:
            val = cfg[Token.HARDWARE][Token.MIDI][Token.CHANNEL]
            # LAME bug in Mod detects MIDI channel as one higher than sent (7 sent, seen by mod as 8) so compensate here
            chan = val - 1 if val > 0 else 0
        except KeyError:
            pass
        return chan

    def __init_midi_default(self):
        self.__init_midi(self.cfg)

    def __init_midi(self, cfg):
        self.midi_channel = self.get_real_midi_channel(cfg)
        # TODO could iterate thru all objects here instead of handling in __init_footswitches
        for ac in self.analog_controls:
            if isinstance(ac, AnalogMidiControl.AnalogMidiControl):
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
                # TODO reusing the footswitch object for multiple pedalboards is not ideal
                # could easily have spillover from a previous pedalboard
                # The mutable data should probably be stored in a separate object and destructed/constructed upon
                # each pedalboard load
                fs.clear_pedalboard_info()

                # Bypass
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
                if Token.PRESET in f:
                    preset_value = f[Token.PRESET]
                    if preset_value == Token.UP:
                        fs.add_preset(callback=self.handler.preset_incr_and_change)
                        fs.set_display_label("Pre+")
                    elif preset_value == Token.DOWN:
                        fs.add_preset(callback=self.handler.preset_decr_and_change)
                        fs.set_display_label("Pre-")
                    elif isinstance(preset_value, int):
                        fs.add_preset(callback=self.handler.preset_set_and_change, callback_arg=preset_value)
                        fs.set_display_label(str(preset_value))

                # LCD/LED attributes
                if Token.COLOR in f:
                    fs.set_lcd_color(f[Token.COLOR])

                # Longpress groups
                if Token.LONGPRESS_GROUPS in f:  # Can be a list or a single (string)
                    fs.set_longpress_groups(Util.DICT_GET(f, Token.LONGPRESS_GROUPS))

                fs.set_callbacks(self.handler.callbacks)

            idx += 1
