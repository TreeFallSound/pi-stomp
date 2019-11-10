#!/usr/bin/env python

import json
import os
import requests as req
import sys
import time

import modalapi.analogswitch as AnalogSwitch
import modalapi.controller as Controller
import modalapi.pedalboard as Pedalboard
import modalapi.util as util

from modalapi.footswitch import Footswitch
from enum import Enum

sys.path.append('/usr/lib/python3.5/site-packages')  # TODO possibly /usr/local/modep/mod-ui
from mod.development import FakeHost as Host

class TopEncoderMode(Enum):
    DEFAULT = 0
    PRESET_SELECT = 1
    PRESET_SELECTED = 2
    PEDALBOARD_SELECT = 3
    PEDALBOARD_SELECTED = 4

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
        self.pedalboard_list = []  # TODO LAME to have two lists
        self.current_pedalboard = None
        self.selected_pedalboard_index = 0

        self.current_presets = {}   # Keyed by index
        self.current_preset_index = 0
        self.selected_preset_index = 0

        self.current_analog_controllers = []

        self.plugin_dict = {}
        self.selected_plugin_index = 0

        # TODO should this be here?
        #self.load_pedalboards()

        # Create dummy host for obtaining pedalboard info
        self.host = Host(None, None, self.msg_callback)

        self.hardware = None

        self.top_encoder_mode = TopEncoderMode.DEFAULT

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
            pedalboard = Pedalboard.Pedalboard(title, bundle)
            pedalboard.load_bundle(bundle, self.plugin_dict)
            self.pedalboards[bundle] = pedalboard
            self.pedalboard_list.append(pedalboard)
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
        footswitch_plugins = []
        pb = self.get_current_pedalboard()
        if pb in self.pedalboards:
            self.current_pedalboard = self.pedalboards[pb]  # TODO right place to do this?
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
                            plugin.controllers.append(controller)
                            if isinstance(controller, Footswitch):
                                # TODO sort this list so selection orders correctly (sort on midi_CC?)
                                plugin.has_footswitch = True
                                footswitch_plugins.append(plugin)
                            else:
                                self.current_analog_controllers.append(controller)
                                print("Controller %s %s", controller, param)

            # Move Footswitch controlled plugins to the end of the list
            self.current_pedalboard.plugins = [elem for elem in self.current_pedalboard.plugins
                                               if elem.has_footswitch is False]
            self.current_pedalboard.plugins += footswitch_plugins

    def load_current_presets(self):

        # Clear existing
        self.current_presets = {}   # Keyed by index
        self.current_preset_index = 0
        self.selected_preset_index = 0

        url = self.root_uri + "pedalpreset/list"
        try:
            resp = req.get(url)
            if resp.status_code == 200:
                pass
        except:
            return None
        dict = json.loads(resp.text)
        for key, name in dict.items():
            if key.isdigit():
                index = int(key)
                self.current_presets[index] = name
        return resp.text

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

    def get_selected_instance(self):
        if self.current_pedalboard is not None:
            pb = self.current_pedalboard
            inst = pb.plugins[self.selected_plugin_index]
            if inst is not None:
                return inst
        return None

    def plugin_select(self, encoder, clk_pin):
        enc = encoder.get_data()
        if self.current_pedalboard is not None:
            pb = self.current_pedalboard
            index = ((self.selected_plugin_index - 1) if (enc is not 1)
                    else (self.selected_plugin_index + 1)) % len(pb.plugins)
            #index = self.next_plugin(pb.plugins, enc)
            plugin = pb.plugins[index]  # TODO check index
            self.selected_plugin_index = index
            self.lcd.draw_plugin_select(plugin)

    def bottom_encoder_sw(self, value):
        if value == AnalogSwitch.Value.RELEASED:
            self.toggle_plugin_bypass()

    def top_encoder_sw(self, value):
        # State machine for top rotary encoder
        mode = self.top_encoder_mode
        if value == AnalogSwitch.Value.RELEASED:
            if mode == TopEncoderMode.PRESET_SELECT:
                self.top_encoder_mode = TopEncoderMode.PEDALBOARD_SELECT
            elif mode == TopEncoderMode.PEDALBOARD_SELECT:
                self.top_encoder_mode = TopEncoderMode.PRESET_SELECT
            elif mode == TopEncoderMode.PRESET_SELECTED:
                self.preset_change()
                self.top_encoder_mode = TopEncoderMode.PRESET_SELECT
            elif mode == TopEncoderMode.PEDALBOARD_SELECTED:
                self.pedalboard_change()
                self.top_encoder_mode = TopEncoderMode.PEDALBOARD_SELECT
            else:
                if len(self.current_presets) > 0:
                    self.top_encoder_mode = TopEncoderMode.PRESET_SELECT
                else:
                    self.top_encoder_mode = TopEncoderMode.PEDALBOARD_SELECT
            self.update_lcd_title()
        elif value == AnalogSwitch.Value.LONGPRESSED:
            self.top_encoder_mode = TopEncoderMode.DEFAULT
            self.update_lcd_title()

    def top_encoder_select(self, encoder, clk_pin):
        # State machine for top encoder switch
        mode = self.top_encoder_mode
        mode = self.top_encoder_mode
        if mode == TopEncoderMode.PEDALBOARD_SELECT or mode == TopEncoderMode.PEDALBOARD_SELECTED:
            self.pedalboard_select(encoder, clk_pin)
            self.top_encoder_mode = TopEncoderMode.PEDALBOARD_SELECTED
        elif mode == TopEncoderMode.PRESET_SELECT or mode == TopEncoderMode.PRESET_SELECTED:
            self.preset_select(encoder, clk_pin)
            self.top_encoder_mode = TopEncoderMode.PRESET_SELECTED

    def pedalboard_select(self, encoder, clk_pin):
        enc = encoder.get_data()
        cur_idx = self.selected_pedalboard_index
        next_idx = ((cur_idx - 1) if (enc is not 1) else (cur_idx + 1)) % len(self.pedalboard_list)
        if self.pedalboard_list[next_idx].bundle in self.pedalboards:
            self.lcd.draw_title(self.pedalboard_list[next_idx].title, None, True, False)
            self.selected_pedalboard_index = next_idx

    def pedalboard_change(self):
        print("Pedalboard change")
        if self.selected_pedalboard_index < len(self.pedalboard_list):
            uri = self.root_uri + "pedalboard/load_bundle/"
            bundlepath = self.pedalboard_list[self.selected_pedalboard_index].bundle
            data = {"bundlepath": bundlepath}
            req.get("http://localhost/reset")
            resp2 = req.post(uri, data)
            if resp2.status_code != 200:
                print("Bad Rest request: %s %s  status: %d" % (uri, data, resp2.status_code))
            self.current_pedalboard = self.pedalboard_list[self.selected_pedalboard_index]

            # Reset "current" data TODO need a better way to do that
            self.current_presets = {}  # Keyed by index
            self.current_preset_index = 0
            self.selected_preset_index = 0

            self.bind_current_pedalboard()
            self.load_current_presets()
            self.update_lcd()

    def toggle_plugin_bypass(self):
        print("toggle_plugin_bypass")
        inst = self.get_selected_instance()
        if inst is not None:
            if inst.has_footswitch:
                for c in inst.controllers:
                    if isinstance(c, Footswitch):
                        c.toggle(0)
                        return
            # Regular (non footswitch plugin)
            url = self.root_uri + "effect/parameter/set//graph%s/:bypass" % inst.instance_id
            value = inst.toggle_bypass()
            try:
                if value:
                    resp = req.post(url, json={"value":"1"})
                else:
                    resp = req.post(url, json={"value":"0"})
                if resp.status_code != 200:
                    print("Bad Rest request: %s status: %d" % (url, resp.status_code))
                    inst.toggle_bypass()  # toggle back to original value since request wasn't successful
            except:
                return
            self.update_lcd_plugins()

    def preset_change_plugin_update(self):
        for p in self.current_pedalboard.plugins:
            uri = self.root_uri + "effect/parameter/get//graph" + p.instance_id + "/:bypass"
            try:
                resp = req.get(uri)
                if resp.status_code == 200:
                    p.set_bypass(resp.text == "true")
            except:
                print("failed to get bypass value for: %s" % p.instance_id)
                continue
        self.lcd.draw_bound_plugins(self.current_pedalboard.plugins)
        self.lcd.draw_plugins(self.current_pedalboard.plugins)
        self.lcd.refresh_plugins()

    def preset_change(self):
        index = self.selected_preset_index
        print("preset change: %d" % index)
        url = "http://localhost/pedalpreset/load?id=%d" % index  # TODO use root and uri (Everywhere)
        # req.get("http://localhost/reset")
        resp = req.get(url)
        if resp.status_code != 200:
            print("Bad Rest request: %s status: %d" % (url, resp.status_code))
        self.current_preset_index = index

        #load of the preset might have changed plugin bypass status
        self.preset_change_plugin_update()

    def next_preset_index(self, dict, current, incr):
        # This essentially applies modulo to a set of potentially discontinuous keys
        # a missing key occurs when a preset is deleted
        indices = list(dict.keys())
        if current not in indices:
            return -1
        cur = indices.index(current)
        if incr:
            if cur < len(indices) - 1:
                return indices[cur + 1]
            return min(indices)
        else:
            if cur > 0:
                return indices[cur - 1]
            return max(indices)

    def preset_select(self, encoder, clk_pin):
        enc = encoder.get_data()
        index = self.next_preset_index(self.current_presets, self.selected_preset_index, enc is not 1)
        if index < 0:
            return
        self.selected_preset_index = index
        self.lcd.draw_title(self.get_current_pedalboard_name(), self.current_presets[index], False, True)

    def update_lcd(self):
        pb_name = self.get_current_pedalboard_name()  # TODO use self.current_pedalboard
        if pb_name is None:
            return

        self.update_lcd_title()

        pb = self.get_current_pedalboard()
        if not pb or self.pedalboards[pb] is None:
            return

        self.lcd.draw_analog_assignments(self.current_analog_controllers)
        self.lcd.draw_plugins(self.pedalboards[pb].plugins)
        self.lcd.draw_bound_plugins(self.pedalboards[pb].plugins)
        self.lcd.refresh_plugins()

    def update_lcd_title(self):
        invert_pb = False
        invert_pre = False
        if self.top_encoder_mode == TopEncoderMode.PEDALBOARD_SELECT:
            invert_pb = True
        if self.top_encoder_mode == TopEncoderMode.PRESET_SELECT:
            invert_pre = True
        self.lcd.draw_title(self.get_current_pedalboard_name(),
                            util.DICT_GET(self.current_presets, self.current_preset_index), invert_pb, invert_pre)

    def update_lcd_plugins(self):
        pb = self.get_current_pedalboard()
        if self.pedalboards[pb] is None:
            return
        self.lcd.draw_plugins(self.pedalboards[pb].plugins)
        self.lcd.refresh_plugins()

    def update_lcd_fs(self):
        pb = self.get_current_pedalboard()
        if self.pedalboards[pb] is None:
            return
        self.lcd.draw_bound_plugins(self.pedalboards[pb].plugins)
