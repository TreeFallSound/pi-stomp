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

from modalapi.analogmidicontrol import AnalogMidiControl
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

class BotEncoderMode(Enum):
    DEFAULT = 0
    DEEP_EDIT = 1
    VALUE_EDIT = 2


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
        self.selected_pedalboard_index = 0
        self.selected_preset_index = 0
        self.selected_plugin_index = 0
        self.selected_parameter_index = 0

        self.plugin_dict = {}

        # TODO should this be here?
        #self.load_pedalboards()

        # Create dummy host for obtaining pedalboard info
        #self.host = Host(None, None, self.msg_callback)
        #def msg_callback(self, msg):
        #    print(msg)

        self.hardware = None

        self.top_encoder_mode = TopEncoderMode.DEFAULT
        self.bot_encoder_mode = BotEncoderMode.DEFAULT

        self.current = None  # pointer to Current class

    # Container for dynamic data which is unique to the "current" pedalboard
    # The self.current pointed above will point to this object which gets
    # replaced when a different pedalboard is made current (old Current object
    # gets deleted and a new one added via self.set_current_pedalboard()
    class Current:
        def __init__(self, pedalboard):
            self.pedalboard = pedalboard
            self.presets = {}
            self.preset_index = 0
            self.analog_controllers = {}  # { type: (plugin_name, param_name) }


    #
    # Hardware
    #

    def add_hardware(self, hardware):
        self.hardware = hardware

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
                self.top_encoder_mode = TopEncoderMode.DEFAULT
            else:
                if len(self.current.presets) > 0:
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
        if mode == TopEncoderMode.PEDALBOARD_SELECT or mode == TopEncoderMode.PEDALBOARD_SELECTED:
            self.pedalboard_select(encoder, clk_pin)
            self.top_encoder_mode = TopEncoderMode.PEDALBOARD_SELECTED
        elif mode == TopEncoderMode.PRESET_SELECT or mode == TopEncoderMode.PRESET_SELECTED:
            self.preset_select(encoder, clk_pin)
            self.top_encoder_mode = TopEncoderMode.PRESET_SELECTED

    def bottom_encoder_sw(self, value):
        # State machine for bottom rotary encoder switch
        mode = self.bot_encoder_mode
        if value == AnalogSwitch.Value.RELEASED:
            if mode == BotEncoderMode.DEFAULT:
                self.toggle_plugin_bypass()
            elif mode == BotEncoderMode.DEEP_EDIT:
                self.bot_encoder_mode = BotEncoderMode.VALUE_EDIT
                self.show_value_edit()

        elif value == AnalogSwitch.Value.LONGPRESSED:
            if mode == BotEncoderMode.DEFAULT:
                self.bot_encoder_mode = BotEncoderMode.DEEP_EDIT
                self.show_deep_edit()
            else:
                self.bot_encoder_mode = BotEncoderMode.DEFAULT
                self.update_lcd()

    def bot_encoder_select(self, encoder, clk_pin):
        mode = self.bot_encoder_mode
        if mode == BotEncoderMode.DEFAULT:
            self.plugin_select(encoder, clk_pin)
        elif mode == BotEncoderMode.DEEP_EDIT:
            self.parameter_select(encoder, clk_pin)

    #
    # Pedalboard Stuff
    #

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

    def get_current_pedalboard_bundle_path(self):
        url = self.root_uri + "pedalboard/current"
        try:
            resp = req.get(url)
            # TODO pass code define
            if resp.status_code == 200:
                return resp.text
        except:
            return None

    def set_current_pedalboard(self, pedalboard):
        # Delete previous "current"
        del self.current

        # Create a new "current"
        self.current = self.Current(pedalboard)

        # Initialize the data
        self.bind_current_pedalboard()
        self.load_current_presets()
        self.update_lcd()

    def bind_current_pedalboard(self):
        # "current" being the pedalboard mod-host says is current
        # The pedalboard data has already been loaded, but this will overlay
        # any real time settings
        footswitch_plugins = []
        if self.current.pedalboard:
            #print(self.current.pedalboard.to_json())
            for plugin in self.current.pedalboard.plugins:
                for sym, param in plugin.parameters.items():
                    if param.binding is not None:
                        controller = self.hardware.controllers.get(param.binding)
                        if controller is not None:
                            # TODO possibly use a setter instead of accessing var directly
                            # What if multiple params could map to the same controller?
                            controller.parameter = param
                            controller.set_value(param.value)
                            plugin.controllers.append(controller)
                            if isinstance(controller, Footswitch):
                                # TODO sort this list so selection orders correctly (sort on midi_CC?)
                                plugin.has_footswitch = True
                                footswitch_plugins.append(plugin)
                            elif isinstance(controller, AnalogMidiControl):
                                self.current.analog_controllers[controller.type] = (plugin.instance_id, param.name)

            # Move Footswitch controlled plugins to the end of the list
            self.current.pedalboard.plugins = [elem for elem in self.current.pedalboard.plugins
                                               if elem.has_footswitch is False]
            self.current.pedalboard.plugins += footswitch_plugins

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
            self.lcd.draw_info_message("Loading...")
            uri = self.root_uri + "pedalboard/load_bundle/"
            bundlepath = self.pedalboard_list[self.selected_pedalboard_index].bundle
            data = {"bundlepath": bundlepath}
            req.get("http://localhost/reset")
            resp2 = req.post(uri, data)
            if resp2.status_code != 200:
                print("Bad Rest request: %s %s  status: %d" % (uri, data, resp2.status_code))

            # Now that it's presumably changed, load the dynamic "current" data
            self.set_current_pedalboard(self.pedalboard_list[self.selected_pedalboard_index])

    #
    # Preset Stuff
    #

    def load_current_presets(self):
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
                self.current.presets[index] = name
        return resp.text

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
        index = self.next_preset_index(self.current.presets, self.selected_preset_index, enc is not 1)
        if index < 0:
            return
        self.selected_preset_index = index
        self.lcd.draw_title(self.current.pedalboard.title, self.current.presets[index], False, True)

    def preset_change(self):
        index = self.selected_preset_index
        print("preset change: %d" % index)
        self.lcd.draw_info_message("Loading...")
        url = "http://localhost/pedalpreset/load?id=%d" % index  # TODO use root and uri (Everywhere)
        # req.get("http://localhost/reset")
        resp = req.get(url)
        if resp.status_code != 200:
            print("Bad Rest request: %s status: %d" % (url, resp.status_code))
        self.current.preset_index = index

        #load of the preset might have changed plugin bypass status
        self.preset_change_plugin_update()

    def preset_change_plugin_update(self):
        # Now that the preset has changed on the host, update plugin bypass indicators
        for p in self.current.pedalboard.plugins:
            uri = self.root_uri + "effect/parameter/get//graph" + p.instance_id + "/:bypass"
            try:
                resp = req.get(uri)
                if resp.status_code == 200:
                    p.set_bypass(resp.text == "true")
            except:
                print("failed to get bypass value for: %s" % p.instance_id)
                continue
        self.lcd.draw_bound_plugins(self.current.pedalboard.plugins)
        self.lcd.draw_plugins(self.current.pedalboard.plugins)
        self.lcd.draw_analog_assignments(self.current.analog_controllers)

    #
    # Plugin Stuff
    #

    def get_selected_instance(self):
        if self.current.pedalboard is not None:
            pb = self.current.pedalboard
            inst = pb.plugins[self.selected_plugin_index]
            if inst is not None:
                return inst
        return None

    def plugin_select(self, encoder, clk_pin):
        enc = encoder.get_data()
        if self.current.pedalboard is not None:
            pb = self.current.pedalboard
            index = ((self.selected_plugin_index - 1) if (enc is not 1)
                    else (self.selected_plugin_index + 1)) % len(pb.plugins)
            #index = self.next_plugin(pb.plugins, enc)
            plugin = pb.plugins[index]  # TODO check index
            self.selected_plugin_index = index
            self.lcd.draw_plugin_select(plugin)

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

    #
    # Deep Edit (Parameter stuff)
    #

    def show_deep_edit(self):
        plugin = self.get_selected_instance()
        print(plugin.parameters)
        self.selected_parameter_index = 0
        self.lcd.draw_deep_edit(plugin.instance_id, plugin.parameters)
        self.lcd.draw_deep_edit_hightlight(self.selected_parameter_index)

    def show_value_edit(self):
        print("show_value_edit: %d" % self.selected_parameter_index)
        if self.selected_parameter_index == 0:
            self.bot_encoder_mode = BotEncoderMode.DEFAULT
            self.update_lcd()
        else:
            pass

    def parameter_select(self, encoder, clk_pin):
        enc = encoder.get_data()
        plugin = self.get_selected_instance()
        index = ((self.selected_parameter_index - 1) if (enc is not 1)
                else (self.selected_parameter_index + 1)) % (len(plugin.parameters) + 1)  # +1 is for the back button
        self.lcd.draw_deep_edit_hightlight(index)
        self.selected_parameter_index = index

    #
    # LCD Stuff
    #

    def update_lcd(self):  # TODO rename to imply the home screen
        self.update_lcd_title()
        self.lcd.draw_analog_assignments(self.current.analog_controllers)
        self.lcd.draw_plugins(self.current.pedalboard.plugins)
        self.lcd.draw_bound_plugins(self.current.pedalboard.plugins)
        self.lcd.draw_plugin_select()

    def update_lcd_title(self):
        invert_pb = False
        invert_pre = False
        if self.top_encoder_mode == TopEncoderMode.PEDALBOARD_SELECT:
            invert_pb = True
        if self.top_encoder_mode == TopEncoderMode.PRESET_SELECT:
            invert_pre = True
        self.lcd.draw_title(self.current.pedalboard.title,
                            util.DICT_GET(self.current.presets, self.current.preset_index), invert_pb, invert_pre)

    def update_lcd_plugins(self):
        self.lcd.draw_plugins(self.current.pedalboard.plugins)

    def update_lcd_fs(self):
        self.lcd.draw_bound_plugins(self.current.pedalboard.plugins)
