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

import json
import logging
import os
import requests as req
import subprocess
import sys
import time
import yaml

import common.token as Token
import common.util as util
import pistomp.analogswitch as AnalogSwitch
import pistomp.encoderswitch as EncoderSwitch
import modalapi.pedalboard as Pedalboard
import modalapi.parameter as Parameter
import modalapi.wifi as Wifi

from pistomp.analogmidicontrol import AnalogMidiControl
from pistomp.footswitch import Footswitch
from pistomp.handler import Handler
from enum import Enum
from pathlib import Path

#sys.path.append('/usr/lib/python3.5/site-packages')  # TODO possibly /usr/local/modep/mod-ui
#from mod.development import FakeHost as Host

class TopEncoderMode(Enum):
    DEFAULT = 0
    PRESET_SELECT = 1
    PRESET_SELECTED = 2
    PEDALBOARD_SELECT = 3
    PEDALBOARD_SELECTED = 4
    SYSTEM_MENU = 5
    HEADPHONE_VOLUME = 6
    INPUT_GAIN = 7

class BotEncoderMode(Enum):
    DEFAULT = 0
    DEEP_EDIT = 1
    VALUE_EDIT = 2

class UniversalEncoderMode(Enum):
    DEFAULT = 0
    SCROLL = 1
    PRESET_SELECT = 2
    PEDALBOARD_SELECT = 3
    PLUGIN_SELECT = 4
    SYSTEM_MENU = 5
    HEADPHONE_VOLUME = 6
    INPUT_GAIN = 7
    EQ1_GAIN = 8
    EQ2_GAIN = 9
    EQ3_GAIN = 10
    EQ4_GAIN = 11
    EQ5_GAIN = 12
    DEEP_EDIT = 13
    VALUE_EDIT = 14
    LOADING = 15

class SelectedType(Enum):
    PEDALBOARD = 0
    PRESET = 1
    PLUGIN = 2
    CONTROLLER = 3
    BYPASS = 4
    WIFI = 5
    SYSTEM = 6
    EQ = 7

# Replace this with menu objects
class MenuType(Enum):
    MENU_NONE = 0
    MENU_SYSTEM = 1
    MENU_INFO = 2
    MENU_AUDIO = 3
    MENU_ADVANCED = 4
    MENU_RESTORE = 5

class Mod(Handler):
    __single = None

    def __init__(self, audiocard, homedir):
        self.wifi_manager = None

        logging.info("Init mod")
        if Mod.__single:
            raise Mod.__single
        Mod.__single = self

        self.audiocard = audiocard
        self.lcd = None
        self.homedir = homedir
        self.root_uri = "http://localhost:80/"

        self.pedalboards = {}
        self.pedalboard_list = []  # TODO LAME to have two lists
        self.selectable_items = []  # List of 2 item tuple (SelectedType, type_specific_index)
        self.selectable_index = 0
        self.selected_pedalboard_index = 0
        self.selected_preset_index = 0
        self.selected_plugin_index = 0
        self.selected_parameter_index = 0
        self.parameter_tweak_amount = 8

        self.plugin_dict = {}

        self.hardware = None

        self.top_encoder_mode = TopEncoderMode.DEFAULT
        self.bot_encoder_mode = BotEncoderMode.DEFAULT
        self.universal_encoder_mode = UniversalEncoderMode.DEFAULT

        self.wifi_status = {}
        self.eq_status = {}
        self.software_version = None
        self.git_describe = None

        self.current = None  # pointer to Current class
        self.deep = None     # pointer to current Deep class

        self.selected_menu_index = 0
        self.menu_items = None
        self.current_menu = MenuType.MENU_NONE

        # This file is modified when the pedalboard is changed via MOD UI
        self.pedalboard_modification_file = "/home/pistomp/data/last.json"
        self.pedalboard_change_timestamp = os.path.getmtime(self.pedalboard_modification_file)\
            if Path(self.pedalboard_modification_file).exists() else 0

        self.wifi_manager = Wifi.WifiManager()

    def __del__(self):
        logging.info("Handler cleanup")
        if self.wifi_manager:
            del self.wifi_manager

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

    class Deep:
        def __init__(self, plugin):
            self.plugin = plugin
            self.parameters = list(plugin.parameters.values()) if plugin is not None else None
            self.selected_parameter_index = 0
            self.selected_parameter = None
            self.value = 0  # TODO shouldn't need this

    #
    # Hardware
    #

    def add_hardware(self, hardware):
        self.hardware = hardware

    def add_lcd(self, lcd):
        self.lcd = lcd


    #
    # Dual Encoder State Machine (used for pi-Stomp v1)
    #
    # Assumption that the top encoder actions can be executed regardless of bottom encoder mode
    # Bottom encoder actions should be ignored while the system menu is active to avoid corrupting the LCD

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
            elif mode == TopEncoderMode.SYSTEM_MENU:
                self.menu_action()
                return
            elif mode == TopEncoderMode.HEADPHONE_VOLUME:
                self.top_encoder_mode = TopEncoderMode.SYSTEM_MENU
            elif mode == TopEncoderMode.INPUT_GAIN:
                self.top_encoder_mode = TopEncoderMode.SYSTEM_MENU
            else:
                if len(self.current.presets) > 0:
                    self.top_encoder_mode = TopEncoderMode.PRESET_SELECT
                else:
                    self.top_encoder_mode = TopEncoderMode.PEDALBOARD_SELECT
            self.update_lcd_title()
        elif value == AnalogSwitch.Value.LONGPRESSED:
            if mode == TopEncoderMode.DEFAULT:
                self.top_encoder_mode = TopEncoderMode.SYSTEM_MENU
                self.system_menu_show()
            else:
                self.top_encoder_mode = TopEncoderMode.DEFAULT
                self.update_lcd()

    def top_encoder_select(self, direction):
        # State machine for top encoder switch
        mode = self.top_encoder_mode
        if mode == TopEncoderMode.PEDALBOARD_SELECT or mode == TopEncoderMode.PEDALBOARD_SELECTED:
            self.pedalboard_select(direction)
            self.top_encoder_mode = TopEncoderMode.PEDALBOARD_SELECTED
        elif mode == TopEncoderMode.PRESET_SELECT or mode == TopEncoderMode.PRESET_SELECTED:
            self.preset_select(direction)
            self.top_encoder_mode = TopEncoderMode.PRESET_SELECTED
        elif mode == TopEncoderMode.SYSTEM_MENU:
            self.menu_select(direction)
        elif mode == TopEncoderMode.HEADPHONE_VOLUME:
            self.parameter_value_change(direction, self.headphone_volume_commit)
        elif mode == TopEncoderMode.INPUT_GAIN:
            self.parameter_value_change(direction, self.input_gain_commit)

    def bottom_encoder_sw(self, value):
        # State machine for bottom rotary encoder switch
        if (self.top_encoder_mode == TopEncoderMode.SYSTEM_MENU or
                self.top_encoder_mode == TopEncoderMode.HEADPHONE_VOLUME or
                self.top_encoder_mode == TopEncoderMode.INPUT_GAIN):
            return  # Ignore bottom encoder if top encoder has navigated to the system menu
        mode = self.bot_encoder_mode
        if value == AnalogSwitch.Value.RELEASED:
            if mode == BotEncoderMode.DEFAULT:
                self.toggle_plugin_bypass()
            elif mode == BotEncoderMode.DEEP_EDIT:
                self.menu_action()
            #elif mode == BotEncoderMode.VALUE_EDIT:
            #    self.parameter_value_change()
        elif value == AnalogSwitch.Value.LONGPRESSED:
            if mode == BotEncoderMode.DEFAULT or BotEncoderMode.VALUE_EDIT:
                self.bot_encoder_mode = BotEncoderMode.DEEP_EDIT
                self.parameter_edit_show()
            else:
                self.bot_encoder_mode = BotEncoderMode.DEFAULT
                self.update_lcd()

    def bot_encoder_select(self, direction):
        if (self.top_encoder_mode == TopEncoderMode.SYSTEM_MENU or
                self.top_encoder_mode == TopEncoderMode.HEADPHONE_VOLUME or
                self.top_encoder_mode == TopEncoderMode.INPUT_GAIN):
            return
        mode = self.bot_encoder_mode
        if mode == BotEncoderMode.DEFAULT:
            self.plugin_select(direction)
        elif mode == BotEncoderMode.DEEP_EDIT:
            self.menu_select(direction)
        elif mode == BotEncoderMode.VALUE_EDIT:
            self.parameter_value_change(direction, self.parameter_value_commit)

    #
    # Universal Encoder State Machine (single encoder navigation for pi-Stomp Core)
    #

    def universal_encoder_sw(self, value):
        # State machine for universal rotary encoder switch
        mode = self.universal_encoder_mode
        if value == EncoderSwitch.Value.RELEASED:
            if mode == UniversalEncoderMode.DEFAULT:
                self.universal_encoder_mode = UniversalEncoderMode.SCROLL
            elif mode == UniversalEncoderMode.SCROLL:
                if self.selected_type() == SelectedType.PLUGIN:
                    self.toggle_plugin_bypass()
                elif self.selected_type() == SelectedType.PEDALBOARD:
                    self.universal_encoder_mode = UniversalEncoderMode.PEDALBOARD_SELECT
                    self.update_lcd_title()
                elif self.selected_type() == SelectedType.PRESET:
                    self.universal_encoder_mode = UniversalEncoderMode.PRESET_SELECT
                    self.update_lcd_title()
                elif self.selected_type() == SelectedType.BYPASS:
                    self.system_toggle_bypass()
                elif self.selected_type() == SelectedType.EQ:
                    self.system_toggle_eq()
                elif self.selected_type() == SelectedType.SYSTEM:
                    self.lcd.clear_select()
                    self.universal_encoder_mode = UniversalEncoderMode.SYSTEM_MENU
                    self.system_menu_show()
            elif mode == UniversalEncoderMode.PEDALBOARD_SELECT:
                self.universal_encoder_mode = UniversalEncoderMode.LOADING
                self.pedalboard_change()
                self.universal_encoder_mode = UniversalEncoderMode.DEFAULT
            elif mode == UniversalEncoderMode.PRESET_SELECT:
                self.universal_encoder_mode = UniversalEncoderMode.LOADING
                self.preset_change()
                self.update_lcd_title()
                self.universal_encoder_mode = UniversalEncoderMode.DEFAULT
            elif mode == UniversalEncoderMode.SYSTEM_MENU:
                self.menu_action()
                return
            elif mode == UniversalEncoderMode.HEADPHONE_VOLUME:
                self.universal_encoder_mode = UniversalEncoderMode.SYSTEM_MENU
                self.system_menu_show()
            elif mode == UniversalEncoderMode.INPUT_GAIN:
                self.universal_encoder_mode = UniversalEncoderMode.SYSTEM_MENU
                self.system_menu_show()
            elif mode == UniversalEncoderMode.EQ1_GAIN:
                self.universal_encoder_mode = UniversalEncoderMode.SYSTEM_MENU
                self.system_audio_menu()
            elif mode == UniversalEncoderMode.EQ2_GAIN:
                self.universal_encoder_mode = UniversalEncoderMode.SYSTEM_MENU
                self.system_audio_menu()
            elif mode == UniversalEncoderMode.EQ3_GAIN:
                self.universal_encoder_mode = UniversalEncoderMode.SYSTEM_MENU
                self.system_audio_menu()
            elif mode == UniversalEncoderMode.EQ4_GAIN:
                self.universal_encoder_mode = UniversalEncoderMode.SYSTEM_MENU
                self.system_audio_menu()
            elif mode == UniversalEncoderMode.EQ5_GAIN:
                self.universal_encoder_mode = UniversalEncoderMode.SYSTEM_MENU
                self.system_audio_menu()
            elif mode == UniversalEncoderMode.DEEP_EDIT:
                self.menu_action()
            elif mode == UniversalEncoderMode.VALUE_EDIT:
                self.universal_encoder_mode = UniversalEncoderMode.DEEP_EDIT
                self.parameter_edit_show(self.selected_menu_index)

        elif value == EncoderSwitch.Value.LONGPRESSED:
            if mode == UniversalEncoderMode.VALUE_EDIT or (mode == UniversalEncoderMode.SCROLL and
                    self.selectable_items[self.selectable_index][0] == SelectedType.PLUGIN):
                self.universal_encoder_mode = UniversalEncoderMode.DEEP_EDIT
                self.parameter_edit_show()
            elif mode == UniversalEncoderMode.DEFAULT:
                self.universal_encoder_mode = UniversalEncoderMode.SYSTEM_MENU
                self.system_menu_show()
            else:
                self.universal_encoder_mode = UniversalEncoderMode.DEFAULT
                self.update_lcd()

    def universal_encoder_select(self, direction):
        # State machine for universal encoder
        mode = self.universal_encoder_mode
        if mode == UniversalEncoderMode.LOADING:
            # ignore rotations when loading
            return
        if mode == UniversalEncoderMode.DEFAULT or mode == UniversalEncoderMode.SCROLL:
            self.universal_encoder_mode = UniversalEncoderMode.SCROLL
            self.universal_select(direction)
        elif mode == UniversalEncoderMode.PEDALBOARD_SELECT:
            self.pedalboard_select(direction)
        elif mode == UniversalEncoderMode.PRESET_SELECT:
            self.preset_select(direction)
        elif mode == UniversalEncoderMode.SYSTEM_MENU:
            self.menu_select(direction)
        elif mode == UniversalEncoderMode.HEADPHONE_VOLUME:
            self.parameter_value_change(direction, self.headphone_volume_commit)
        elif mode == UniversalEncoderMode.INPUT_GAIN:
            self.parameter_value_change(direction, self.input_gain_commit)
        elif mode == UniversalEncoderMode.EQ1_GAIN:
            self.parameter_value_change(direction, self.eq1_gain_commit)
        elif mode == UniversalEncoderMode.EQ2_GAIN:
            self.parameter_value_change(direction, self.eq2_gain_commit)
        elif mode == UniversalEncoderMode.EQ3_GAIN:
            self.parameter_value_change(direction, self.eq3_gain_commit)
        elif mode == UniversalEncoderMode.EQ4_GAIN:
            self.parameter_value_change(direction, self.eq4_gain_commit)
        elif mode == UniversalEncoderMode.EQ5_GAIN:
            self.parameter_value_change(direction, self.eq5_gain_commit)
        elif mode == UniversalEncoderMode.DEEP_EDIT:
            self.menu_select(direction)
        elif mode == UniversalEncoderMode.VALUE_EDIT:
            self.parameter_value_change(direction, self.parameter_value_commit)

    def universal_select(self, direction):
        if self.current.pedalboard is not None:
            prev_type = self.selectable_items[self.selectable_index][0]
            index = ((self.selectable_index + 1) if (direction == 1)
                     else (self.selectable_index - 1)) % len(self.selectable_items)
            self.selectable_index = index
            item_type = self.selectable_items[index][0]

            # Clear previous selection
            if item_type != prev_type:
                if prev_type == SelectedType.PLUGIN:
                    self.lcd.draw_plugin_select(None)
                elif prev_type == SelectedType.PEDALBOARD or prev_type == SelectedType.PRESET:
                    self.update_lcd_title()
                elif prev_type == SelectedType.BYPASS or prev_type == SelectedType.SYSTEM or prev_type == SelectedType.EQ:
                    self.lcd.clear_select()

            # Select new item
            if item_type == SelectedType.PEDALBOARD:
                self.pedalboard_select(0)
            elif item_type == SelectedType.PRESET:
                self.preset_select(0)
            elif item_type == SelectedType.PLUGIN:
                plugin_index = self.selectable_items[index][1]
                self.selected_plugin_index = plugin_index
                plugin = self.current.pedalboard.plugins[plugin_index]
                self.lcd.draw_plugin_select(plugin)
            elif item_type == SelectedType.BYPASS:
                self.lcd.draw_tool_select(SelectedType.BYPASS)
            elif item_type == SelectedType.EQ:
                self.lcd.draw_tool_select(SelectedType.EQ)
            elif item_type == SelectedType.SYSTEM:
                self.lcd.draw_tool_select(SelectedType.SYSTEM)

    def selected_type(self):
        return self.selectable_items[self.selectable_index][0]

    def poll_controls(self):
        if self.universal_encoder_mode is not UniversalEncoderMode.LOADING:
            self.hardware.poll_controls()
        wifi_update = self.wifi_manager.poll()
        if wifi_update is not None:
            self.wifi_status = wifi_update
            self.lcd.update_wifi(self.wifi_status)
            if self.current_menu == MenuType.MENU_INFO:
                self.system_info_update_wifi()
        output = subprocess.check_output(["amixer", "get", "DAC EQ"])
        if "off" in output.decode("utf-8"):
            self.eq_status = False
        else:
            self.eq_status = True
        self.lcd.update_eq(self.eq_status)

    def poll_modui_changes(self):
        # This poll looks for changes made via the MOD UI and tries to sync the pi-Stomp hardware

        # Look for a change of pedalboard
        #
        # If the pedalboard_modification_file timestamp has changed, extract the bundle path and set current pedalboard
        #
        # TODO this is an interim solution until better MOD-UI to pi-stomp event communication is added
        #
        if Path(self.pedalboard_modification_file).exists():
            ts = os.path.getmtime(self.pedalboard_modification_file)
            if ts == self.pedalboard_change_timestamp:
                return

            # Timestamp changed
            self.pedalboard_change_timestamp = ts
            self.lcd.draw_info_message("Loading...")
            mod_bundle = self.get_pedalboard_bundle_from_mod()
            if mod_bundle:
                logging.info("Pedalboard changed via MOD from: %s to: %s" %
                             (self.current.pedalboard.bundle, mod_bundle))
                pb = self.pedalboards[mod_bundle]
                self.set_current_pedalboard(pb)

    #
    # Pedalboard Stuff
    #

    def load_pedalboards(self):
        url = self.root_uri + "pedalboard/list"

        try:
            resp = req.get(url)
        except:  # TODO
            logging.error("Cannot connect to mod-host")
            sys.exit()

        if resp.status_code != 200:
            logging.error("Cannot connect to mod-host.  Status: %s" % resp.status_code)
            sys.exit()

        pbs = json.loads(resp.text)
        for pb in pbs:
            logging.info("Loading pedalboard info: %s" % pb[Token.TITLE])
            bundle = pb[Token.BUNDLE]
            title = pb[Token.TITLE]
            pedalboard = Pedalboard.Pedalboard(title, bundle)
            pedalboard.load_bundle(bundle, self.plugin_dict)
            self.pedalboards[bundle] = pedalboard
            self.pedalboard_list.append(pedalboard)
            #logging.debug("dump: %s" % pedalboard.to_json())

        # TODO - example of querying host
        #bund = self.get_current_pedalboard()
        #self.host.load(bund, False)
        #logging.debug("Preset: %s %d" % (bund, self.host.pedalboard_preset))  # this value not initialized
        #logging.debug("Preset: %s" % self.get_current_preset_name())

    def get_pedalboard_bundle_from_mod(self):
        # Assumes the caller has already checked for existence of the file
        mod_bundle = None
        with open(self.pedalboard_modification_file, 'r') as file:
            j = json.load(file)
            mod_bundle = util.DICT_GET(j, 'pedalboard')
        return mod_bundle

    def get_current_pedalboard_bundle_path(self):
        mod_bundle = None
        if Path(self.pedalboard_modification_file).exists():
            mod_bundle = self.get_pedalboard_bundle_from_mod()
        return mod_bundle

    def set_current_pedalboard(self, pedalboard):
        # Delete previous "current"
        del self.current

        # Create a new "current"
        self.current = self.Current(pedalboard)

        # Load Pedalboard specific config (overrides default set during initial hardware init)
        config_file = Path(pedalboard.bundle) / "config.yml"
        cfg = None
        if config_file.exists():
            with open(config_file.as_posix(), 'r') as ymlfile:
                cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
        self.hardware.reinit(cfg)

        # Initialize the data
        self.bind_current_pedalboard()
        self.load_current_presets()
        self.update_lcd()

        # Selection info
        self.selectable_items.clear()
        self.selectable_items.append((SelectedType.PEDALBOARD, None))
        if len(self.current.presets) > 0:
            self.selectable_items.append((SelectedType.PRESET, None))
        for i in range(len(self.current.pedalboard.plugins)):
            self.selectable_items.append((SelectedType.PLUGIN, i))
        if self.lcd.supports_toolbar:
            self.selectable_items.append((SelectedType.EQ, None))
            self.selectable_items.append((SelectedType.BYPASS, None))
            self.selectable_items.append((SelectedType.SYSTEM, None))
        self.selectable_index = 0
        self.selected_preset_index = 0

    def bind_current_pedalboard(self):
        # "current" being the pedalboard mod-host says is current
        # The pedalboard data has already been loaded, but this will overlay
        # any real time settings
        footswitch_plugins = []
        if self.current.pedalboard:
            #logging.debug(self.current.pedalboard.to_json())
            for plugin in self.current.pedalboard.plugins:
                if plugin is None or plugin.parameters is None:
                    continue
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
                                key = "%s:%s" % (plugin.instance_id, param.name)
                                controller.cfg[Token.CATEGORY] = plugin.category  # somewhat LAME adding to cfg dict
                                controller.cfg[Token.TYPE] = controller.type
                                self.current.analog_controllers[key] = controller.cfg

            # Move Footswitch controlled plugins to the end of the list
            self.current.pedalboard.plugins = [elem for elem in self.current.pedalboard.plugins
                                               if elem.has_footswitch is False]
            self.current.pedalboard.plugins += footswitch_plugins

    def pedalboard_select(self, direction):
        # 0 means the pedalboard field is selected but a new pedalboard hasn't been scrolled to yet
        if direction == 0:
            self.lcd.draw_title(self.current.pedalboard.title, None, True, False)
            return
        cur_idx = self.selected_pedalboard_index
        next_idx = ((cur_idx - 1) if (direction == 1) else (cur_idx + 1)) % len(self.pedalboard_list)
        if self.pedalboard_list[next_idx].bundle in self.pedalboards:
            highlight_only = self.universal_encoder_mode == UniversalEncoderMode.PEDALBOARD_SELECT
            self.lcd.draw_title(self.pedalboard_list[next_idx].title, None, True, False, highlight_only)
            self.selected_pedalboard_index = next_idx

    def pedalboard_change(self):
        logging.info("Pedalboard change")
        if self.selected_pedalboard_index < len(self.pedalboard_list):
            self.lcd.draw_info_message("Loading...")

            resp1 = req.get(self.root_uri + "reset")
            if resp1.status_code != 200:
                logging.error("Bad Reset request")

            uri = self.root_uri + "pedalboard/load_bundle/"
            bundlepath = self.pedalboard_list[self.selected_pedalboard_index].bundle
            data = {"bundlepath": bundlepath}
            resp2 = req.post(uri, data)
            if resp2.status_code != 200:
                logging.error("Bad Rest request: %s %s  status: %d" % (uri, data, resp2.status_code))

            # Now that it's presumably changed, load the dynamic "current" data
            self.set_current_pedalboard(self.pedalboard_list[self.selected_pedalboard_index])
            self.bot_encoder_mode = BotEncoderMode.DEFAULT

    #
    # Preset Stuff
    #

    def load_current_presets(self):
        url = self.root_uri + "snapshot/list"
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

    def preset_select(self, direction):
        index = self.selected_preset_index
        # 0 means the preset field is selected but a new preset hasn't been scrolled to yet
        if direction != 0:
            index = self.next_preset_index(self.current.presets, self.selected_preset_index, direction == 1)
        self.preset_select_index(index)

    def preset_select_index(self, index):
        if index < 0 or index >= len(self.current.presets):
            return None
        self.selected_preset_index = index
        preset_name = self.current.presets[index]
        highlight_only = self.universal_encoder_mode == UniversalEncoderMode.PRESET_SELECT
        self.lcd.draw_title(self.current.pedalboard.title, preset_name, False, True, highlight_only)
        return preset_name

    def preset_change(self):
        index = self.selected_preset_index
        logging.info("preset change: %d" % index)
        self.lcd.draw_info_message("Loading...")
        url = (self.root_uri + "snapshot/load?id=%d" % index)
        # req.get(self.root_uri + "reset")
        resp = req.get(url)
        if resp.status_code != 200:
            logging.error("Bad Rest request: %s status: %d" % (url, resp.status_code))
        self.current.preset_index = index

        #load of the preset might have changed plugin bypass status
        self.preset_change_plugin_update()
        self.bot_encoder_mode = BotEncoderMode.DEFAULT

    def preset_incr_and_change(self):
        if self.universal_encoder_mode == UniversalEncoderMode.LOADING:
            return
        self.universal_encoder_mode = UniversalEncoderMode.LOADING
        self.preset_select(1)
        self.preset_change()
        self.universal_encoder_mode = UniversalEncoderMode.DEFAULT

    def preset_decr_and_change(self):
        if self.universal_encoder_mode == UniversalEncoderMode.LOADING:
            return
        self.universal_encoder_mode = UniversalEncoderMode.LOADING
        self.preset_select(-1)
        self.preset_change()
        self.universal_encoder_mode = UniversalEncoderMode.DEFAULT

    def preset_set_and_change(self, index):
        if self.universal_encoder_mode == UniversalEncoderMode.LOADING:
            return
        self.universal_encoder_mode = UniversalEncoderMode.LOADING
        if self.preset_select_index(index):
            self.preset_change()
        self.universal_encoder_mode = UniversalEncoderMode.DEFAULT

    def preset_change_plugin_update(self):
        # Now that the preset has changed on the host, update plugin bypass indicators
        for p in self.current.pedalboard.plugins:
            uri = self.root_uri + "effect/parameter/pi_stomp_get//graph" + p.instance_id + "/:bypass"
            try:
                resp = req.get(uri)
                if resp.status_code == 200:
                    p.set_bypass(resp.text == "true")
            except:
                logging.error("failed to get bypass value for: %s" % p.instance_id)
                continue
        self.lcd.draw_tools(SelectedType.WIFI, SelectedType.EQ, SelectedType.BYPASS, SelectedType.SYSTEM)
        self.lcd.draw_analog_assignments(self.current.analog_controllers)
        self.lcd.draw_plugins(self.current.pedalboard.plugins)
        self.lcd.draw_bound_plugins(self.current.pedalboard.plugins, self.hardware.footswitches)
        self.lcd.draw_plugin_select()

    #
    # Plugin Stuff
    #

    def get_selected_instance(self):
        if self.current.pedalboard is not None:
            pb = self.current.pedalboard
            if self.selected_plugin_index < len(pb.plugins):
                inst = pb.plugins[self.selected_plugin_index]
                if inst is not None:
                    return inst
        return None

    def plugin_select(self, direction):
        if self.current.pedalboard is not None:
            pb = self.current.pedalboard
            index = ((self.selected_plugin_index + 1) if (direction == 1)
                    else (self.selected_plugin_index - 1)) % len(pb.plugins)
            #index = self.next_plugin(pb.plugins, enc)
            plugin = pb.plugins[index]  # TODO check index
            self.selected_plugin_index = index
            self.lcd.draw_plugin_select(plugin)

    def toggle_plugin_bypass(self):
        logging.debug("toggle_plugin_bypass")
        inst = self.get_selected_instance()
        if inst is not None:
            if inst.has_footswitch:
                for c in inst.controllers:
                    if isinstance(c, Footswitch):
                        c.pressed(0)
                        return
            # Regular (non footswitch plugin)
            url = self.root_uri + "effect/parameter/pi_stomp_set//graph%s/:bypass" % inst.instance_id
            value = inst.toggle_bypass()
            code = self.parameter_set_send(url, "1" if value else "0", 200)
            if (code != 200):
                inst.toggle_bypass()  # toggle back to original value since request wasn't successful

            #  Indicate change on LCD, and redraw selection(highlight)
            self.update_lcd_plugins()
            self.lcd.draw_plugin_select(inst)  # Not strictly required for original pi-stomp

    #
    # Generic Menu functions
    #

    def menu_select(self, direction):
        tried = 0
        num = len(self.menu_items)
        index = self.selected_menu_index
        sort_list = list(sorted(self.menu_items))

        # incr/decr to next item having a non-None action
        while tried < num:
            index = ((index - 1) if (direction != 1) else (index + 1)) % num
            item = sort_list[index]
            action = self.menu_items[item][Token.ACTION]
            if action is not None:
                break
            tried = tried + 1

        self.lcd.menu_highlight(index)
        self.selected_menu_index = index

    def menu_action(self):
        item = list(sorted(self.menu_items))[self.selected_menu_index]
        action = self.menu_items[item][Token.ACTION]
        if action is not None:
            action()

    def menu_back(self):
        self.current_menu = MenuType.MENU_NONE
        self.top_encoder_mode = TopEncoderMode.DEFAULT
        self.bot_encoder_mode = BotEncoderMode.DEFAULT
        self.universal_encoder_mode = UniversalEncoderMode.DEFAULT
        self.update_lcd()

    #
    # System Menu
    #

    def system_info_load(self):
        try:
            output = subprocess.check_output(['git', '--git-dir', self.homedir + '/.git',
                                              '--work-tree', self.homedir, 'describe'])
            if output:
                self.git_describe = output.decode()
                self.software_version = self.git_describe.split('-')[0]
        except subprocess.CalledProcessError:
            logging.error("Cannot obtain git software tag info")

    def system_menu_show(self):
        self.current_menu = MenuType.MENU_SYSTEM
        self.menu_items = {"0": {Token.NAME: "< Back to main screen", Token.ACTION: self.menu_back},
                           "1": {Token.NAME: "System shutdown", Token.ACTION: self.system_menu_shutdown},
                           "2": {Token.NAME: "System reboot", Token.ACTION: self.system_menu_reboot},
                           "3": {Token.NAME: "System info", Token.ACTION: self.system_info_show},
                           "4": {Token.NAME: "Save current pedalboard", Token.ACTION: self.system_menu_save_current_pb},
                           "5": {Token.NAME: "Reload pedalboards", Token.ACTION: self.system_menu_reload},
                           "6": {Token.NAME: "Restart sound engine", Token.ACTION: self.system_menu_restart_sound},
                           "7": {Token.NAME: "Audio Options", Token.ACTION: self.system_audio_menu},
                           "8": {Token.NAME: "Advanced Settings", Token.ACTION: self.system_advanced_menu}}
        self.lcd.menu_show("System menu", self.menu_items)
        # Trick: we display the wifi status in the menu, Ideally we need a better
        # state handling to know what needs to be displayed or not based on whether
        # we have a menu or not. For example a "Page" object that corresponds to
        # the content of the LCD, one that has all the normal screen objects,
        # one that has the menu(s) etc... and we have a "current page". That way
        # we can do updates to state without clobbering the current page.
        # Right now, wifi updates will clobber the menu so may as well always
        # display the wifi state.
        self.lcd.update_wifi(self.wifi_status)
        self.selected_menu_index = 0
        self.lcd.menu_highlight(0)

    def system_info_populate_wifi(self):
        hotspot_active = False
        key = 'hotspot_active'
        if key in self.wifi_status:
            self.menu_items[key] = {Token.NAME: self.wifi_status[key], Token.ACTION: None}
            if self.wifi_status[key]:
                hotspot_active = True
        key = 'ip_address'
        if key in self.wifi_status:
            self.menu_items["ip_addr"] = {Token.NAME: self.wifi_status[key], Token.ACTION: None}
        else:
            self.menu_items["ip_addr"] = {Token.NAME: '<unknown>', Token.ACTION: None}
        self.menu_items.pop("Enable Hotspot", None)
        self.menu_items.pop("Disable Hotspot", None)
        if hotspot_active:
            self.menu_items["Disable Hotspot"] = {Token.NAME: "", Token.ACTION: self.system_disable_hotspot}
        else:
            self.menu_items["Enable Hotspot"] = {Token.NAME: "", Token.ACTION: self.system_enable_hotspot}

    def system_info_show(self):
        self.current_menu = MenuType.MENU_INFO
        self.menu_items = {"0": {Token.NAME: "< Back to main screen", Token.ACTION: self.menu_back}}
        self.menu_items["SW:"] = {Token.NAME: self.git_describe, Token.ACTION: None}
        self.system_info_populate_wifi()
        self.lcd.menu_show("System Info", self.menu_items)
        # See comment in system_menu_show()
        self.lcd.update_wifi(self.wifi_status)
        self.selected_menu_index = 0
        self.lcd.menu_highlight(0)

    def system_info_update_wifi(self):
        self.system_info_populate_wifi()
        self.lcd.menu_show("System Info", self.menu_items)
        self.lcd.update_wifi(self.wifi_status)
        self.lcd.menu_highlight(self.selected_menu_index)

    def system_disable_hotspot(self):
        self.lcd.draw_info_message("Disabling, please wait...")
        self.wifi_manager.disable_hotspot()

    def system_enable_hotspot(self):
        self.lcd.draw_info_message("Enabling, please wait...")
        self.wifi_manager.enable_hotspot()
    
    def system_advanced_menu(self):
        self.current_menu = MenuType.MENU_ADVANCED
        self.menu_items = {"0": {Token.NAME: "< Back to main screen", Token.ACTION: self.menu_back},
                           "1": {Token.NAME: "Backup user data", Token.ACTION: self.user_backup_data},
                           "2": {Token.NAME: "Restore user data", Token.ACTION: self.user_restore_data},
                           "3": {Token.NAME: "System Update", Token.ACTION: self.system_update}}
        self.lcd.menu_show("Advanced Settings", self.menu_items)
        self.selected_menu_index = 0
        self.lcd.menu_highlight(0)
        
    def system_audio_menu(self):
        output = subprocess.check_output(["amixer", "get", "DAC EQ"])
        if "off" in output.decode("utf-8"):
            eq_status = False
        else:
            eq_status = True
        if eq_status:
            self.current_menu = MenuType.MENU_AUDIO
            self.lcd.menu_show("Audio Options", self.menu_items)
            self.menu_items = {"0": {Token.NAME: "< Back to main screen", Token.ACTION: self.menu_back},
                                "1": {Token.NAME: "Input Gain", Token.ACTION: self.system_menu_input_gain},
                                "2": {Token.NAME: "Output Volume", Token.ACTION: self.system_menu_headphone_volume},
                                "3": {Token.NAME: "Low Band Gain", Token.ACTION: self.system_menu_eq1_volume},
                                "4": {Token.NAME: "Low-Mid Band Gain", Token.ACTION: self.system_menu_eq2_volume},
                                "5": {Token.NAME: "Mid Band Gain", Token.ACTION: self.system_menu_eq3_volume},
                                "6": {Token.NAME: "Mid-High Band Gain", Token.ACTION: self.system_menu_eq4_volume},
                                "7": {Token.NAME: "High Band Gain", Token.ACTION: self.system_menu_eq5_volume}}
            self.menu_global_eq_toggle()
            self.menu_items.pop("Reset Global EQ", None)
            self.menu_items["Reset Global EQ"] = {Token.NAME: "", Token.ACTION: self.reset_eq_values}
            self.lcd.menu_show("Audio Options", self.menu_items)
        else:
            self.current_menu = MenuType.MENU_AUDIO
            self.lcd.menu_show("Audio Options", self.menu_items)
            self.menu_items = {"0": {Token.NAME: "< Back to main screen", Token.ACTION: self.menu_back},
                                "1": {Token.NAME: "Input Gain", Token.ACTION: self.system_menu_input_gain},
                                "2": {Token.NAME: "Output Volume", Token.ACTION: self.system_menu_headphone_volume}}
            self.menu_global_eq_toggle()
            self.menu_items.pop("Reset Global EQ", None)
            self.menu_items["Reset Global EQ"] = {Token.NAME: "", Token.ACTION: self.reset_eq_values}
            self.lcd.menu_show("Audio Options", self.menu_items)
        self.selected_menu_index = 0
        self.lcd.menu_highlight(0)

    def menu_global_eq_toggle(self):
        self.lcd.menu_show("Audio Options", self.menu_items)
        output = subprocess.check_output(["amixer", "get", "DAC EQ"])
        if "off" in output.decode("utf-8"):
            eq_status = False
        else:
            eq_status = True
        self.menu_items.pop("Enable Global EQ", None)
        self.menu_items.pop("Disable Global EQ", None)
        if eq_status:
            self.menu_items["Disable Global EQ"] = {Token.NAME: "", Token.ACTION: self.system_disable_eq}
        else:
            self.menu_items["Enable Global EQ"] = {Token.NAME: "", Token.ACTION: self.system_enable_eq}

    def reset_eq_values(self):
        os.system('sudo amixer sset "DAC EQ1" 13') # This sets the gain the same as with the EQ disabled
        os.system('sudo amixer sset "DAC EQ2" 13')
        os.system('sudo amixer sset "DAC EQ3" 13')
        os.system('sudo amixer sset "DAC EQ4" 13')
        os.system('sudo amixer sset "DAC EQ5" 13')
        os.system('sudo alsactl store')
        self.lcd.draw_info_message("EQ Bands reset")
        self.system_info_update_eq()
        self.lcd.menu_highlight(0)

    def system_disable_eq(self):
        os.system('sudo amixer sset "DAC EQ" mute')
        os.system('sudo alsactl store')
        self.lcd.draw_info_message("Disabling, please wait...")
        self.eq_status = False
        self.system_info_update_eq()

    def system_enable_eq(self):
        os.system('sudo amixer sset "DAC EQ" unmute')
        os.system('sudo alsactl store')
        self.lcd.draw_info_message("Enabling, please wait...")
        self.eq_status = True
        self.system_info_update_eq()
    
    def system_toggle_eq(self):
        os.system('sudo amixer sset "DAC EQ" toggle')
        os.system('sudo alsactl store')

    def system_info_update_eq(self):
        self.menu_global_eq_toggle()
        self.system_audio_menu()
        self.lcd.update_eq(self.eq_status)
        self.lcd.menu_show("Audio Options", self.menu_items)
        self.lcd.menu_highlight(self.selected_menu_index)

    def system_menu_save_current_pb(self):
        logging.debug("save current")
        # TODO this works to save the pedalboard values, but just default, not Preset values
        # Figure out how to save preset (host.py:preset_save_replace)
        # TODO this also causes a problem if self.current.pedalboard.title != mod-host title
        # which can happen if the pedalboard is changed via MOD UI, not via hardware
        url = self.root_uri + "pedalboard/save"
        try:
            resp = req.post(url, data={"asNew": "0", "title": self.current.pedalboard.title})
            if resp.status_code != 200:
                logging.error("Bad Rest request: %s status: %d" % (url, resp.status_code))
            else:
                logging.debug("saved")
        except:
            logging.error("status %s" % resp.status_code)
            return

    def system_menu_reload(self):
        logging.info("Exiting main process, systemctl should restart if enabled")
        sys.exit(0)

    def system_menu_restart_sound(self):
        self.lcd.splash_show()
        logging.info("Restart sound engine (jack)")
        os.system('sudo systemctl restart jack')

    def system_menu_shutdown(self):
        self.lcd.splash_show(False)
        logging.info("System Shutdown")
        os.system('sudo amixer sset "AUX Jack" mute')
        os.system('sudo alsactl store')
        os.system('sudo systemctl --no-wall poweroff')

    def system_menu_reboot(self):
        self.lcd.splash_show(False)
        logging.info("System Reboot")
        os.system('sudo amixer sset "AUX Jack" mute')
        os.system('sudo alsactl store')
        os.system('sudo systemctl reboot')

    def check_usb(self):
        self.usbflash = False
        backup_folder = '/media/usb0/backups'
        if not os.path.exists(backup_folder):
            os.mkdir(backup_folder)
        stat = subprocess.call(["systemctl", "is-active", "--quiet", "usbmount@dev-sda1"])
        if(stat == 0):
            self.usbflash = True
        else:
            self.usbflash = False

    def user_backup_data(self):
        self.check_usb()
        if self.usbflash:
            self.lcd.draw_info_message("Backing up, please wait...")
            os.system('zip -rq "/media/usb0/backups/pistomp_backup.zip" ~pistomp/data -x ~pistomp/data/.lv2')
            self.current_menu = MenuType.MENU_ADVANCED
            self.lcd.menu_show("Advanced Settings", self.menu_items)
        else:
            return

    def user_restore_data(self):
        self.check_usb()
        if self.usbflash:
            directory = '/media/usb0/backups'
            filename = 'pistomp_backup.zip'
            self.current_menu = MenuType.MENU_RESTORE
            self.lcd.menu_show("Restore Files", self.menu_items)
            self.menu_items = {"0": {Token.NAME: "< Back to main screen", Token.ACTION: self.system_advanced_menu}}
            if os.path.exists(os.path.join(directory, filename)):
                self.menu_items.pop(filename, None)
                self.menu_items[filename] = {Token.NAME: "", Token.ACTION: self.do_restore}
            self.lcd.menu_show("Restore Files", self.menu_items)
            self.selected_menu_index = 0
            self.lcd.menu_highlight(0)
        else:
            logging.error("Error, no backups found...")
            return

    def do_restore(self):
        self.lcd.draw_info_message("Restoring, please wait...")
        os.system('unzip -o -u /media/usb0/backups/pistomp_backup.zip -d ~pistomp/')
        self.lcd.menu_show("Restore Files", self.menu_items)

    def system_update(self):
        dir = '/home/pistomp/pi-stomp'
        username = "pistomp"
        command = ["git", "-C", dir, "pull"]
        self.lcd.draw_info_message("Updating, please wait...")
        subprocess.run(['sudo', '-u', username, '--'] + command)
        self.current_menu = MenuType.MENU_ADVANCED
        self.lcd.menu_show("Advanced Settings", self.menu_items)
        sys.exit(0)

    def system_menu_input_gain(self):
        title = "Input Gain"
        self.top_encoder_mode = TopEncoderMode.INPUT_GAIN
        self.universal_encoder_mode = UniversalEncoderMode.INPUT_GAIN
        info = {"shortName": title, "symbol": "igain", "ranges": {"minimum": -19.75, "maximum": 12}}
        self.system_menu_parameter(title, self.audiocard.CAPTURE_VOLUME, info)

    def system_menu_headphone_volume(self):
        title = "Headphone Volume"
        self.top_encoder_mode = TopEncoderMode.HEADPHONE_VOLUME
        self.universal_encoder_mode = UniversalEncoderMode.HEADPHONE_VOLUME
        info = {"shortName": title, "symbol": "hvol", "ranges": {"minimum": -25.75, "maximum": 6}}
        self.system_menu_parameter(title, self.audiocard.MASTER, info)

    def system_menu_eq1_volume(self):
        title = "Low Band Gain"
        self.universal_encoder_mode = UniversalEncoderMode.EQ1_GAIN
        info = {"shortName": title, "symbol": "egain", "ranges": {"minimum": -10.50, "maximum": 12}}
        self.system_menu_parameter(title, self.audiocard.EQ_1, info)

    def system_menu_eq2_volume(self):
        title = "Low-Mid Band Gain"
        self.universal_encoder_mode = UniversalEncoderMode.EQ2_GAIN
        info = {"shortName": title, "symbol": "egain", "ranges": {"minimum": -10.50, "maximum": 12}}
        self.system_menu_parameter(title, self.audiocard.EQ_2, info)

    def system_menu_eq3_volume(self):
        title = "Mid Band Gain"
        self.universal_encoder_mode = UniversalEncoderMode.EQ3_GAIN
        info = {"shortName": title, "symbol": "egain", "ranges": {"minimum": -10.50, "maximum": 12}}
        self.system_menu_parameter(title, self.audiocard.EQ_3, info)

    def system_menu_eq4_volume(self):
        title = "Mid-High Band Gain"
        self.universal_encoder_mode = UniversalEncoderMode.EQ4_GAIN
        info = {"shortName": title, "symbol": "egain", "ranges": {"minimum": -10.50, "maximum": 12}}
        self.system_menu_parameter(title, self.audiocard.EQ_4, info)

    def system_menu_eq5_volume(self):
        title = "High Band Gain"
        self.universal_encoder_mode = UniversalEncoderMode.EQ5_GAIN
        info = {"shortName": title, "symbol": "egain", "ranges": {"minimum": -10.50, "maximum": 12}}
        self.system_menu_parameter(title, self.audiocard.EQ_5, info)

    def system_menu_parameter(self, title, param_name, info):
        value = self.audiocard.get_parameter(param_name)
        self.deep = self.Deep(None)
        param = Parameter.Parameter(info, value, None)
        self.deep.selected_parameter = param
        self.lcd.draw_value_edit_graph(param, value)
        self.lcd.draw_info_message(title)

    def input_gain_commit(self):
        self.audiocard.set_parameter(self.audiocard.CAPTURE_VOLUME, self.deep.selected_parameter.value)

    def headphone_volume_commit(self):
        self.audiocard.set_parameter(self.audiocard.MASTER, self.deep.selected_parameter.value)

    def eq1_gain_commit(self):
        self.audiocard.set_parameter(self.audiocard.EQ_1, self.deep.selected_parameter.value)

    def eq2_gain_commit(self):
        self.audiocard.set_parameter(self.audiocard.EQ_2, self.deep.selected_parameter.value)

    def eq3_gain_commit(self):
        self.audiocard.set_parameter(self.audiocard.EQ_3, self.deep.selected_parameter.value)

    def eq4_gain_commit(self):
        self.audiocard.set_parameter(self.audiocard.EQ_4, self.deep.selected_parameter.value)

    def eq5_gain_commit(self):
        self.audiocard.set_parameter(self.audiocard.EQ_5, self.deep.selected_parameter.value)

    def system_toggle_bypass(self):
        relay = self.hardware.relay
        footswitch = None
        # if a footswitch is assigned to control a relay, use it
        for fs in self.hardware.footswitches:
            for r in fs.relay_list:
                relay = r
                footswitch = fs
                break

        if relay is not None:
            if relay.enabled:
                relay.disable()
            else:
                relay.enable()
            self.lcd.update_bypass(relay.enabled)

            if footswitch is not None:
                # Update LED
                footswitch.set_value(int(not relay.enabled))

    #
    # Parameter Edit
    #

    def parameter_edit_show(self, selected=0):
        plugin = self.get_selected_instance()
        self.deep = self.Deep(plugin)  # TODO this creates a new obj every time menu is shown, singleton?
        self.deep.selected_parameter_index = 0
        self.menu_items = {0: {Token.NAME: "< Back to main screen", Token.ACTION: self.menu_back}}
        i = 1
        for p in self.deep.parameters:
            if p.symbol == ":bypass":
                continue
            self.menu_items[i] = {Token.NAME: p.name,
                                       Token.ACTION: self.parameter_value_show,
                                       Token.PARAMETER: p}
            i = i + 1
        self.lcd.menu_show(plugin.instance_id, self.menu_items)
        self.selected_menu_index = selected
        self.lcd.menu_highlight(selected)

    def parameter_value_show(self):
        self.bot_encoder_mode = BotEncoderMode.VALUE_EDIT
        self.universal_encoder_mode = UniversalEncoderMode.VALUE_EDIT
        item = list(sorted(self.menu_items))[self.selected_menu_index]
        if not item:
            return
        param = self.menu_items[item][Token.PARAMETER]
        self.deep.selected_parameter = param
        self.lcd.draw_value_edit(self.deep.plugin.instance_id, param, param.value)

    def parameter_value_change(self, direction, commit_callback):
        param = self.deep.selected_parameter
        value = float(param.value)
        # TODO tweak value won't change from call to call, cache it
        tweak = util.renormalize_float(self.parameter_tweak_amount, 0, 127, param.minimum, param.maximum)
        new_value = round(((value - tweak) if (direction != 1) else (value + tweak)), 2)
        if new_value > param.maximum:
            new_value = param.maximum
        if new_value < param.minimum:
            new_value = param.minimum
        if new_value is value:
            return
        self.deep.selected_parameter.value = new_value  # TODO somewhat risky to change value before committed
        commit_callback()
        self.lcd.draw_value_edit_graph(param, new_value)

    def parameter_value_commit(self):
        param = self.deep.selected_parameter
        url = self.root_uri + "effect/parameter/pi_stomp_set//graph%s/%s" % (self.deep.plugin.instance_id, param.symbol)
        formatted_value = ("%.1f" % param.value)
        self.parameter_set_send(url, formatted_value, 200)

    def parameter_set_send(self, url, value, expect_code):
        logging.debug("request: %s" % url)
        try:
            resp = None
            if value is not None:
                logging.debug("value: %s" % value)
                resp = req.post(url, json={"value": value})
            if resp.status_code != expect_code:
                logging.error("Bad Rest request: %s status: %d" % (url, resp.status_code))
            else:
                logging.debug("Parameter changed to: %d" % value)
        except:
            logging.debug("status: %s" % resp.status_code)
            return resp.status_code

    #
    # LCD Stuff
    #

    def update_lcd(self):  # TODO rename to imply the home screen
        self.lcd.draw_tools(SelectedType.WIFI, SelectedType.EQ, SelectedType.BYPASS, SelectedType.SYSTEM)
        self.lcd.update_bypass(self.hardware.relay.enabled)
        self.lcd.update_eq(self.eq_status)
        self.update_lcd_title()
        self.lcd.draw_analog_assignments(self.current.analog_controllers)
        self.lcd.draw_plugins(self.current.pedalboard.plugins)
        self.lcd.draw_bound_plugins(self.current.pedalboard.plugins, self.hardware.footswitches)
        self.lcd.draw_plugin_select()

    def update_lcd_title(self):
        invert_pb = False
        invert_pre = False
        highlight_only = False
        if self.top_encoder_mode == TopEncoderMode.PEDALBOARD_SELECT or \
                self.universal_encoder_mode == UniversalEncoderMode.PEDALBOARD_SELECT:
            invert_pb = True
        if self.top_encoder_mode == TopEncoderMode.PRESET_SELECT or \
                self.universal_encoder_mode == UniversalEncoderMode.PRESET_SELECT:
            invert_pre = True
        if self.universal_encoder_mode == UniversalEncoderMode.PEDALBOARD_SELECT or \
                self.universal_encoder_mode == UniversalEncoderMode.PRESET_SELECT:
            highlight_only = True
        self.lcd.draw_title(self.current.pedalboard.title,
            util.DICT_GET(self.current.presets, self.current.preset_index), invert_pb, invert_pre, highlight_only)

    def update_lcd_plugins(self):
        self.lcd.draw_plugins(self.current.pedalboard.plugins)

    def update_lcd_fs(self, bypass_change=False):
        if bypass_change:
            self.lcd.update_bypass(self.hardware.relay.enabled)
        self.lcd.draw_bound_plugins(self.current.pedalboard.plugins, self.hardware.footswitches)
