#!/usr/bin/env python

import json
import os
import requests as req
import sys

import modalapi.controller as Controller
import modalapi.pedalboard as Pedalboard

sys.path.append('/usr/lib/python3.5/site-packages')  # TODO possibly /usr/local/modep/mod-ui
from mod.development import FakeHost as Host


class Mod:
    __single = None

    def __init__(self, lcd):
        print("Init mod")
        if Mod.__single:
            raise Mod.__single
        Mod.__single = self

        self.lcd = lcd
        self.root_uri = "http://localhost:80/"
        self.pedalboards = {}  # TODO make the ordering of entries deterministic
        self.controllers = {}  # Keyed by midi_channel:midi_CC
        self.current_pedalboard = None
        self.current_preset_index = 0
        self.current_num_presets = 4

        self.plugin_dict = {}

        # TODO should this be here?
        #self.load_pedalboards()

        # Create dummy host for obtaining pedalboard info
        self.host = Host(None, None, self.msg_callback)

        self.hardware = None

    def add_hardware(self, hardware):
        self.hardware = hardware

    def msg_callback(self, msg):
        print(msg)

    def load_pedalboards(self):
        url = self.root_uri + "pedalboard/list"

        try:
            resp = req.get(url)
        except:  # TODO
            print("Cannot connect to mod-host.")
            sys.exit()

        if resp.status_code != 200:
            print("Cannot connect to mod-host.  Status: %s" % resp.status_code)
            sys.exit()

        pbs = json.loads(resp.text)
        for pb in pbs:
            print("Loading pedalboard info: %s" % pb['title'])
            bundle = pb['bundle']
            title = pb['title']
            pedalboard = Pedalboard.Pedalboard(bundle, title)
            pedalboard.load_bundle(bundle, self.plugin_dict)
            self.pedalboards[bundle] = pedalboard
            #print("dump: %s" % pedalboard.to_json())

        # TODO - example of querying host
        #bund = self.get_current_pedalboard()
        #self.host.load(bund, False)
        #print("Preset: %s %d" % (bund, self.host.pedalboard_preset))  # this value not initialized
        #print("Preset: %s" % self.get_current_preset_name())

    def bind_current_pedalboard(self):
        # "current" being the pedalboard mod-host says is current
        # The pedalboard data has already been loaded, but this will overlay
        # any real time settings
        pb = self.get_current_pedalboard()
        if pb in self.pedalboards:
            self.current_pedalboard = self.pedalboards[pb]
            print("set current PB as: %s" % self.current_pedalboard)
            #print(self.current_pedalboard.to_json())
            for plugin in self.current_pedalboard.plugins:
                for sym, param in plugin.parameters.items():
                    if param.binding is not None:
                        controller = self.hardware.controllers.get(param.binding)
                        if controller is not None:
                            #print("Map: %s %s %s" % (plugin.instance_id, param.name, param.binding))
                            # TODO possibly use a setter instead of accessing var directly
                            # What if multiple params could map to the same controller?
                            controller.parameter = param
                            controller.set_value(param.value)

    # TODO change these functions ripped from modep
    def get_current_pedalboard(self):
        url = self.root_uri + "pedalboard/current"
        try:
            resp = req.get(url)
            # TODO pass code define
            if resp.status_code == 200:
                return resp.text
        except:
            return None

    def get_current_pedalboard_name(self):
        pb = self.get_current_pedalboard()
        return os.path.splitext(os.path.basename(pb))[0]

    # TODO remove
    def get_current_pedalboard_index(self, pedalboards, current):
        try:
            return pedalboards.index(current)
        except:
            return None


    # TODO doesn't seem to work without host being properly initialized
    def get_current_preset_name(self):
        return self.host.pedalpreset_name(self.current_preset_index)

    def preset_change(self, encoder, clk_pin):
        enc = encoder.get_data()
        index = ((self.current_preset_index - 1) if (enc == 1)
                 else (self.current_preset_index + 1)) % self.current_num_presets
        print("preset change: %d" % index)
        url = "http://localhost/pedalpreset/load?id=%d" % index
        print(url)
        # req.get("http://localhost/reset")
        resp = req.get(url)
        if resp.status_code != 200:
            print("Bad Rest request: %s status: %d" % (url, resp.status_code))
        self.current_preset_index = index

        # TODO move formatting to common place
        # TODO name varaibles so they don't have to be calculated
        text = "%s-%s" % (self.get_current_pedalboard_name(), self.get_current_preset_name())
        self.lcd.draw_title(text)
        self.update_lcd()  # TODO just update zone0

    def update_lcd(self):
        print("draw LCD")
        pb_name = self.get_current_pedalboard_name()
        if pb_name is None:
            return
        title = "%s-%s" % (self.get_current_pedalboard_name(), self.get_current_preset_name())
        self.lcd.draw_title(title)
        self.lcd.refresh_zone(0)
        pb = self.get_current_pedalboard()
        if self.pedalboards[pb] is None:
            return
        self.lcd.draw_plugins(self.pedalboards[pb].plugins)
        self.lcd.refresh_zone(1)
        self.lcd.refresh_zone(2)
        self.lcd.refresh_zone(3)

    def update_lcd1(self):
        print("updating LCD")
        #title = "%s-%s" % (self.get_current_pedalboard_name(), self.get_current_preset_name())
        #self.lcd.draw_title(title)
        self.lcd.draw_plugins(self.pedalboards[self.get_current_pedalboard()].plugins)
        self.lcd.refresh()
