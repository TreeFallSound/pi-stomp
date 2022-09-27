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

from pistomp.handler import Handler

import json
import logging
import os
import requests as req
import subprocess
import sys
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
from pistomp.lcd320x240 import Lcd
from enum import Enum
from pathlib import Path


class Modhandler(Handler):
    __single = None

    def __init__(self, audiocard, homedir):
        self.wifi_manager = None

        logging.info("Init modhandler")
        if Modhandler.__single:
            raise Modhandler.__single
        Modhandler.__single = self

        self.audiocard = audiocard

        self.homedir = homedir
        self.root_uri = "http://localhost:80/"
        self.hardware = None

        self.pedalboards = {}
        self.pedalboard_list = []  # TODO LAME to have two lists
        self.plugin_dict = {}

        self.current = None  # pointer to Current class
        self.lcd = None

        # This file is modified when the pedalboard is changed via MOD UI
        self.pedalboard_modification_file = "/home/pistomp/data/last.json"
        self.pedalboard_change_timestamp = os.path.getmtime(self.pedalboard_modification_file)\
            if Path(self.pedalboard_modification_file).exists() else 0

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

    def add_hardware(self, hardware):
        self.hardware = hardware

    def add_lcd(self, lcd):
        self.lcd = lcd

    def poll_controls(self):
        if self.hardware:
            self.hardware.poll_controls()

    def universal_encoder_select(self, direction):
        if self.lcd is not None:
            self.lcd.enc_step(direction)

    def universal_encoder_sw(self, value):
        if self.lcd is not None:
            self.lcd.enc_sw(value)

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

        # Initialize the data and draw on LCD
        self.bind_current_pedalboard()
        self.load_current_presets()
        #self.lcd.init_data(self.pedalboard_list, pedalboard,
        #                   self.current.presets, self.current.preset_index)
        self.lcd.link_data(self.pedalboard_list, self.current)
        self.lcd.draw_main_panel()

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

    def pedalboard_change(self, pedalboard=None):
        logging.info("Pedalboard change")
        self.lcd.draw_info_message("Loading...")

        resp1 = req.get(self.root_uri + "reset")
        if resp1.status_code != 200:
            logging.error("Bad Reset request")

        uri = self.root_uri + "pedalboard/load_bundle/"

        if pedalboard is None:
            pedalboard = self.pedalboard_list[0]
        self.set_current_pedalboard(pedalboard)
        bundlepath = pedalboard.bundle
        data = {"bundlepath": bundlepath}
        resp2 = req.post(uri, data)
        if resp2.status_code != 200:
            logging.error("Bad Rest request: %s %s  status: %d" % (uri, data, resp2.status_code))

        # Now that it's presumably changed, load the dynamic "current" data
        self.set_current_pedalboard(pedalboard)

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

    def preset_change(self, index):
        logging.info("preset change: %d" % index)
        self.lcd.draw_info_message("Loading...")
        url = (self.root_uri + "snapshot/load?id=%d" % index)
        # req.get(self.root_uri + "reset")
        resp = req.get(url)
        if resp.status_code != 200:
            logging.error("Bad Rest request: %s status: %d" % (url, resp.status_code))
        self.current.preset_index = index

        # Update name on lcd
        self.lcd.draw_title()

        # load of the preset might have changed plugin bypass status
        self.preset_change_plugin_update()

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
        self.lcd.refresh_plugins()

    #
    # Plugin Stuff
    #
    def toggle_plugin_bypass(self, event, widget, plugin):
        logging.debug("toggle_plugin_bypass")
        if plugin is not None:
            if plugin.has_footswitch:
                for c in plugin.controllers:
                    if isinstance(c, Footswitch):
                        c.pressed(0)
                        return
            # Regular (non footswitch plugin)
            url = self.root_uri + "effect/parameter/pi_stomp_set//graph%s/:bypass" % plugin.instance_id
            value = plugin.toggle_bypass()
            code = self.parameter_set_send(url, "1" if value else "0", 200)
            if (code != 200):
                plugin.toggle_bypass()  # toggle back to original value since request wasn't successful

            #  Indicate change on LCD
            self.lcd.toggle_plugin(widget, plugin)

    #
    # Parameter Stuff
    #
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

    def system_menu_reload(self, arg):
        logging.info("Exiting main process, systemctl should restart if enabled")
        sys.exit(0)

    def system_menu_shutdown(self):
        self.lcd.splash_show(False)
        logging.info("System Shutdown")
        os.system('sudo systemctl --no-wall poweroff')

    def system_menu_reboot(self):
        self.lcd.splash_show(False)
        logging.info("System Reboot")
        os.system('sudo systemctl reboot')
