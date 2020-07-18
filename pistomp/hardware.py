#!/usr/bin/env python3

import logging
import os
import yaml

import pistomp.analogmidicontrol
import pistomp.token as Token

DEFAULT_CONFIG_FILE = "default_config.yml"


class Hardware:

    def __init__(self, mod, midiout, refresh_callback):
        logging.debug("Init hardware")

        self.mod = mod
        self.midiout = midiout
        self.refresh_callback = refresh_callback

        # From config file(s)
        self.default_cfg = None  # default
        self.cfg = None          # compound cfg (default with user/pedalboard specific cfg overlaid)
        self.midi_channel = 0

        # Standard hardware objects (not required to exist)
        self.analog_controls = []
        self.encoders = []
        self.controllers = {}
        self.footswitches = []

        # Read the default cfg
        self.__load_default_cfg()

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

    def __load_default_cfg(self):
        # Read the default config file - should only need to read once per session
        script_dir = os.path.dirname(os.path.realpath(__file__))
        default_config_file = os.path.join(script_dir, DEFAULT_CONFIG_FILE)
        with open(default_config_file, 'r') as ymlfile:
            self.default_cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)

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
                        fs.set_display_label("Up")
                    if preset_value == Token.DOWN:
                        fs.add_preset(callback=self.mod.preset_decr_and_change)
                        fs.set_display_label("Down")
            idx += 1


