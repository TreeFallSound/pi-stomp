#!/usr/bin/env python3

import RPi.GPIO as GPIO
import json
import spidev
import yaml

import modalapi.analogmidicontrol as AnalogMidiControl
import modalapi.analogswitch as AnalogSwitch
import modalapi.controller as Controller
import modalapi.encoder as Encoder
import modalapi.footswitch as Footswitch
import modalapi.relay as Relay
import modalapi.token as Token
import modalapi.util as util

# Midi
# TODO move to default_config.yml
MIDI_CHANNEL = 13  # Note that a learned MIDI msg will report as the channel +1 (MOD bug?)

# Pins
TOP_ENC_PIN_D = 17
TOP_ENC_PIN_CLK = 4
TOP_ENC_SWITCH_CHANNEL = 7
BOT_ENC_PIN_D = 22
BOT_ENC_PIN_CLK = 27
BOT_ENC_SWITCH_CHANNEL = 6
ENC_SW_THRESHOLD = 512

RELAY_LEFT_PIN = 16
RELAY_RIGHT_PIN = 12

# Each footswitch defined by a quad touple:
# 1: id (left = 0, mid = 1, right = 2)
# 2: the GPIO pin it's attached to
# 3: the associated LED output pin and
# 4: the MIDI Control (CC) message that will be sent when the switch is toggled
# Pin modifications should only be made if the hardware is changed accordingly
FOOTSW = ((0, 23, 24, 61), (1, 25, 0, 62), (2, 13, 26, 63))

# TODO replace in default_config.yml
# Analog Controls defined by a triple touple:
# 1: the ADC channel
# 2: the minimum threshold for considering the value to be changed
# 3: the MIDI Control (CC) message that will be sent
# 4: control type (KNOB, EXPRESSION, etc.)
# Tweak, Expression Pedal
ANALOG_CONTROL = ((0, 16, 64, 'KNOB'), (1, 16, 65, 'EXPRESSION'))

class Hardware:
    __single = None

    def __init__(self, mod, midiout, refresh_callback):
        print("Init hardware")
        if Hardware.__single:
            raise Hardware.__single
        Hardware.__single = self

        self.mod = mod
        self.analog_controls = []
        self.encoders = []
        self.controllers = {}
        self.footswitches = []
        self.midiout = midiout
        self.refresh_callback = refresh_callback
        self.cfg = None

        # Create Relay objects
        self.relay_left = Relay.Relay(RELAY_LEFT_PIN)
        self.relay_right = Relay.Relay(RELAY_RIGHT_PIN)


        GPIO.setmode(GPIO.BCM)  # TODO should this go earlier?

        # Create Footswitches
        for f in FOOTSW:
            fs = Footswitch.Footswitch(f[0], f[1], f[2], f[3], MIDI_CHANNEL, midiout,
                                       refresh_callback=self.refresh_callback)
            self.footswitches.append(fs)

        # Read the default config file and initialize footswitches
        default_config_file = "/home/modep/modalapi/.default_config.yml"
        with open(default_config_file, 'r') as ymlfile:
            self.cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
        self.__init_footswitches_default()

        # Initialize Analog inputs
        spi = spidev.SpiDev()
        spi.open(0, 1)  # Bus 0, CE1
        spi.max_speed_hz = 1000000  # TODO match with LCD or don't specify.  Move to top of file
        for c in ANALOG_CONTROL:
            control = AnalogMidiControl.AnalogMidiControl(spi, c[0], c[1], c[2], MIDI_CHANNEL, midiout, c[3])
            self.analog_controls.append(control)
            key = format("%d:%d" % (MIDI_CHANNEL, c[2]))
            self.controllers[key] = control  # Controller.Controller(MIDI_CHANNEL, c[1], Controller.Type.ANALOG)

        # Initialize Encoders
        top_enc = Encoder.Encoder(TOP_ENC_PIN_D, TOP_ENC_PIN_CLK, callback=mod.top_encoder_select)
        self.encoders.append(top_enc)
        bot_enc = Encoder.Encoder(BOT_ENC_PIN_D, BOT_ENC_PIN_CLK, callback=mod.bot_encoder_select)
        self.encoders.append(bot_enc)
        control = AnalogSwitch.AnalogSwitch(spi, TOP_ENC_SWITCH_CHANNEL, ENC_SW_THRESHOLD, callback=mod.top_encoder_sw)
        self.analog_controls.append(control)
        control = AnalogSwitch.AnalogSwitch(spi, BOT_ENC_SWITCH_CHANNEL, ENC_SW_THRESHOLD, callback=mod.bottom_encoder_sw)
        self.analog_controls.append(control)

    def poll_controls(self):
        # This is intended to be called periodically from main working loop to poll the instantiated controls
        for c in self.analog_controls:
            c.refresh()
        for e in self.encoders:
            e.read_rotary()

    def reinit_footswitches(self, cfg):
        self.__init_footswitches_default()
        self.__init_footswitches(cfg)

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
                # Bypass
                fs.clear_relays()
                if Token.BYPASS in f:
                    if f[Token.BYPASS] == Token.LEFT_RIGHT or f[Token.BYPASS] == Token.LEFT:
                        fs.add_relay(self.relay_left)
                    if f[Token.BYPASS] == Token.LEFT_RIGHT or f[Token.BYPASS] == Token.RIGHT:
                        fs.add_relay(self.relay_right)

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
                        fs.set_midi_CC(cc)
                        key = format("%d:%d" % (MIDI_CHANNEL, fs.midi_CC))
                        self.controllers[key] = fs   # TODO problem if this creates a new element?

                # Preset Control
                fs.clear_preset()
                if Token.PRESET in f:
                    if f[Token.PRESET] == Token.UP:
                        fs.add_preset(callback=self.mod.preset_incr_and_change)
            idx += 1

