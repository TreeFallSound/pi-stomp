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
import modalapi.pedalboard as Pedalboard
import modalapi.wifi as Wifi
import pistomp.settings as Settings

from pistomp.analogmidicontrol import AnalogMidiControl
from pistomp.encodermidicontrol import EncoderMidiControl
from pistomp.footswitch import Footswitch
from pistomp.handler import Handler
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
        self.settings = Settings.Settings()

        self.pedalboards = {}
        self.pedalboard_list = []  # TODO LAME to have two lists
        self.plugin_dict = {}

        self.wifi_status = {}
        self.eq_status = {}
        self.bypass_left = False
        self.bypass_right = False

        self.current = None  # pointer to Current class
        self.lcd = None

        # Banks
        self.banks_file = "/home/pistomp/data/banks.json"
        self.banks_file_timestamp = os.path.getmtime(self.banks_file) if Path(self.banks_file).exists() else 0
        self.banks = {}
        self.current_bank = None

        # This file is modified when the pedalboard is changed via MOD UI
        self.pedalboard_modification_file = "/home/pistomp/data/last.json"
        self.pedalboard_change_timestamp = os.path.getmtime(self.pedalboard_modification_file)\
            if Path(self.pedalboard_modification_file).exists() else 0

        self.wifi_manager = Wifi.WifiManager()

        # Callback function map.  Key is the user specified name, value is function from this handler
        # Used for calling handler callbacks pointed to by names which may be user set in the config file
        self.callbacks = {"set_mod_tap_tempo": self.set_mod_tap_tempo,
                          "next_snapshot": self.preset_incr_and_change,
                          "previous_snapshot": self.preset_decr_and_change,
                          "toggle_bypass": self.system_toggle_bypass,
                          "toggle_tap_tempo_enable": self.toggle_tap_tempo_enable
        }

    def __del__(self):
        logging.info("Handler cleanup")
        if self.wifi_manager:
            del self.wifi_manager
    def cleanup(self):
        if self.lcd is not None:
            self.lcd.cleanup()
        if self.hardware is not None:
            self.hardware.cleanup()

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

    def poll_indicators(self):
        if self.hardware:
            self.hardware.poll_indicators()

    def poll_wifi(self):
        wifi_update = self.wifi_manager.poll()
        if wifi_update is not None:
            self.wifi_status = wifi_update
            self.lcd.update_wifi(self.wifi_status)

    def poll_lcd_updates(self):
        if self.lcd:
            self.lcd.poll_updates()

    def universal_encoder_select(self, direction):
        if self.lcd is not None:
            self.lcd.enc_step(direction)

    def universal_encoder_sw(self, value, obj=None):
        if self.lcd is not None:
            self.lcd.enc_sw(value)

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
            if ts != self.pedalboard_change_timestamp:
                # Timestamp changed
                self.pedalboard_change_timestamp = ts
                self.lcd.draw_info_message("Loading...")
                mod_bundle = self.get_pedalboard_bundle_from_mod()
                if mod_bundle:
                    logging.info("Pedalboard changed via MOD from: %s to: %s" %
                                 (self.current.pedalboard.bundle, mod_bundle))
                    pb = self.reload_pedalboard(mod_bundle)
                    self.set_current_pedalboard(pb)

        # Look for a change in banks file
        if Path(self.banks_file).exists():
            ts = os.path.getmtime(self.banks_file)
            if ts != self.banks_file_timestamp:
                # Timestamp changed
                logging.info("Reloading banks file: %s" % self.banks_file)
                self.banks_file_timestamp = ts
                self.load_banks()

    #
    # Bank Stuff
    #
    def load_banks(self):
        self.current_bank = self.settings.get_setting(Token.BANK)
        if Path(self.banks_file).exists():
            with open(self.banks_file, 'r') as file:
                self.banks = {}
                j = json.load(file)
                for bd in j:
                    bank = util.DICT_GET(bd, 'title')
                    pbs = util.DICT_GET(bd, 'pedalboards')
                    b = self.banks[bank] = []
                    for p in pbs:
                        title = util.DICT_GET(p, 'title')
                        b.append(title)

    def get_banks(self):
        return self.banks

    def get_bank(self):
        return self.current_bank

    def set_bank(self, bank_name):
        self.current_bank = bank_name
        self.settings.set_setting(Token.BANK, bank_name)

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

    def reload_pedalboard(self, bundle):
        # find the current pedalboard object associated with that bundle
        old = self.pedalboards[bundle]
        title = old.title

        # create a new one
        pedalboard = Pedalboard.Pedalboard(title, bundle)
        pedalboard.load_bundle(bundle, self.plugin_dict)
        self.pedalboards[bundle] = pedalboard

        # replace the pedalboard in pedalboard_list with the new one
        try:
            index = self.pedalboard_list.index(old)
        except:
            logging.error("Cannot locate pedalboard: %s", title)
        else:
            self.pedalboard_list[index] = pedalboard
        del old

        return pedalboard

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
        self.lcd.link_data(self.pedalboard_list, self.current, self.hardware.footswitches)
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
                                controller.set_category(plugin.category)
                            elif isinstance(controller, AnalogMidiControl):
                                key = "%s:%s" % (plugin.instance_id, param.name)
                                controller.cfg[Token.CATEGORY] = plugin.category  # somewhat LAME adding to cfg dict
                                controller.cfg[Token.TYPE] = controller.type
                                controller.cfg[Token.ID] = controller.id
                                self.current.analog_controllers[key] = controller.cfg
                            elif isinstance(controller, EncoderMidiControl):
                                key = "%s:%s" % (plugin.instance_id, param.name)
                                controller.cfg[Token.CATEGORY] = plugin.category  # somewhat LAME adding to cfg dict
                                controller.cfg[Token.TYPE] = controller.type
                                controller.cfg[Token.ID] = controller.id
                                self.current.analog_controllers[key] = controller.cfg

            # LAME special case for volume control
            # Doesn't seem quite right to add this here, but it's where all the mapped controls are bound
            for e in self.hardware.encoders:
                if e.type == Token.VOLUME:
                    cfg = {
                        Token.CATEGORY : None,
                        Token.TYPE : e.type,
                        Token.ID : e.id
                    }
                    self.current.analog_controllers[Token.VOLUME] = cfg

    def pedalboard_change(self, pedalboard=None):
        logging.info("Pedalboard change")
        self.lcd.draw_info_message("Loading...")

        resp1 = req.get(self.root_uri + "reset")
        if resp1.status_code != 200:
            logging.error("Bad Reset request")

        uri = self.root_uri + "pedalboard/load_bundle/"

        if pedalboard is None:
            pedalboard = self.pedalboard_list[0]
        #self.set_current_pedalboard(pedalboard)  # TODO is this necessary?
        bundlepath = pedalboard.bundle
        data = {"bundlepath": bundlepath}
        resp2 = req.post(uri, data)
        if resp2.status_code != 200:
            logging.error("Bad Rest request: %s %s  status: %d" % (uri, data, resp2.status_code))

        # Now that it's presumably changed, load the dynamic "current" data
        # TODO this seems to be no longer required since the MOD pedalboard change will call this via poll_modui_changes()
        #self.set_current_pedalboard(pedalboard)

    #
    # Preset Stuff
    #
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

    def load_current_presets(self):
        url = self.root_uri + "snapshot/list"
        try:
            resp = req.get(url)
            if resp.status_code == 200:
                pass
        except:
            return None
        ret = resp.text
        dict = json.loads(resp.text)
        for key, name in dict.items():
            if key.isdigit():
                index = int(key)
                self.current.presets[index] = name

        # Get current snapshot (preset) info
        url = self.root_uri + "snapshot/name?id=current"  # this will fail (500) for non pi-stomp versions of mod-ui
        try:
            resp = req.get(url)
        except:
            return None
        if resp.status_code == 200 and resp.text is not None:
            current_snapshot_name = util.DICT_GET(json.loads(resp.text), "name")
            for i, n in self.current.presets.items():
                if n == current_snapshot_name:
                    self.current.preset_index = i
                    break

        return ret

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

    def preset_incr_and_change(self, *argv):
        index = self.next_preset_index(self.current.presets, self.current.preset_index, True)
        self.preset_change(index)

    def preset_decr_and_change(self, *argv):
        index = self.next_preset_index(self.current.presets, self.current.preset_index, False)
        self.preset_change(index)

    #
    # Plugin Stuff
    #
    def toggle_plugin_bypass(self, widget, plugin):
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
    def update_lcd_fs(self, footswitch=None, bypass_change=False):
        self.lcd.update_footswitch(footswitch)

    def get_num_footswitches(self):
        return len(self.hardware.footswitches)

    #
    # Parameter Stuff
    #
    def parameter_value_commit(self, param, value):
        param.value = value
        url = self.root_uri + "effect/parameter/pi_stomp_set//graph%s/%s" % (param.instance_id, param.symbol)
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

    def parameter_midi_change(self, param, direction):
        if param:
            d = self.lcd.draw_parameter_dialog(param)
            if d:
                self.lcd.enc_step_widget(d, direction)

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

        self.eq_status = self.audiocard.get_switch_parameter(self.audiocard.DAC_EQ)
        self.lcd.update_eq(self.eq_status)
        if self.hardware.relay is not None:
            enabled = not self.hardware.relay.get()
            self.lcd.update_bypass(enabled, enabled)
            # We assume here that if hardware has a physical relay there's no reason to do audiocard bypass (below)
        else:
            self.bypass_left = self.audiocard.get_bypass_left()
            self.bypass_right = self.audiocard.get_bypass_right()
            self.lcd.update_bypass(self.bypass_left, self.bypass_right)

    def system_menu_shutdown(self, arg):
        self.lcd.splash_show(False)
        logging.info("System Shutdown")
        os.system('sudo systemctl --no-wall poweroff')

    def system_menu_reboot(self, arg):
        self.lcd.splash_show(False)
        logging.info("System Reboot")
        os.system('sudo systemctl reboot')

    def system_menu_save_current_pb(self, arg):
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

    def system_menu_reload(self, arg):
        logging.info("Exiting main process, systemctl should restart if enabled")
        sys.exit(0)

    def system_menu_restart_sound(self, arg):
        self.lcd.splash_show()
        logging.info("Restart sound engine (jack)")
        os.system('sudo systemctl restart jack')

    def system_disable_eq(self):
        self.lcd.draw_info_message("Disabling, please wait...")
        success = self.audiocard.set_switch_parameter(self.audiocard.DAC_EQ, False)
        if success:
            self.eq_status = False
        # TODO self.system_info_update_eq()

    def system_enable_eq(self):
        self.lcd.draw_info_message("Enabling, please wait...")
        success = self.audiocard.set_switch_parameter(self.audiocard.DAC_EQ, True)
        if success:
            self.eq_status = True
        # TODO self.system_info_update_eq()

    def system_toggle_eq(self, arg):
        to_status = not self.eq_status
        if to_status:
            self.system_enable_eq()
        else:
            self.system_disable_eq()

    def system_toggle_bypass(self, arg=None):
        if self.hardware.relay is not None:
            enabled = self.hardware.relay.get()
            self.hardware.relay.update(not enabled)
            self.lcd.update_bypass(enabled, enabled)
            # We assume here that if hardware has a physical relay there's no reason to do audiocard bypass (below)
            return

        bypass_preference = self.settings.get_setting(Token.BYPASS)
        if bypass_preference is None or bypass_preference == Token.LEFT or bypass_preference == Token.LEFT_RIGHT:
            self.bypass_left = not self.bypass_left
            self.audiocard.set_bypass_left(self.bypass_left)
        if bypass_preference is None or bypass_preference == Token.RIGHT or bypass_preference == Token.LEFT_RIGHT:
            self.bypass_right = not self.bypass_right
            self.audiocard.set_bypass_right(self.bypass_right)
        self.lcd.update_bypass(self.bypass_left, self.bypass_right)

    def change_bypass_preference(self, pref):
        self.settings.set_setting(Token.BYPASS, pref)

    def system_toggle_hotspot(self):
        if util.DICT_GET(self.wifi_status, 'hotspot_active'):
            self.wifi_manager.disable_hotspot()
        else:
            self.wifi_manager.enable_hotspot()

    def audio_parameter_change(self, direction, name, symbol, value, min, max, commit_callback):
        if symbol is not None:
            d = self.lcd.draw_audio_parameter_dialog(name, symbol, value, min, max, commit_callback)
            if d is not None:
                self.lcd.enc_step_widget(d, direction)

    def system_menu_input_gain(self, arg):
        value = self.audiocard.get_volume_parameter(self.audiocard.CAPTURE_VOLUME)
        self.lcd.draw_audio_parameter_dialog("Input Gain", self.audiocard.CAPTURE_VOLUME, value,
                                             -19.75, 12, self.audio_parameter_commit)

    def system_menu_headphone_volume(self, arg):
        value = self.audiocard.get_volume_parameter(self.audiocard.MASTER)
        if arg is None:
            arg = 0
        self.audio_parameter_change(arg, "Output Volume", self.audiocard.MASTER, value,
                                             -25.75, 6, self.audio_parameter_commit)

    def system_menu_vu_calibration(self, arg):
        value = self.settings.get_setting('analogVU.adc_baseline')
        self.lcd.draw_vu_calibration_dialog('analogVU.adc_baseline', value,
                                            commit_callback=self.settings_file_commit)

    def settings_file_commit(self, symbol, value):
        self.settings.set_setting(symbol, value)
        self.hardware.recalibrateVU_baseline(value)

    def system_menu_eq1_gain(self, arg):
        value = self.audiocard.get_volume_parameter(self.audiocard.EQ_1)
        self.lcd.draw_audio_parameter_dialog("Low Band Gain", self.audiocard.EQ_1, value,
                                             -10.50, 12, self.audio_parameter_commit)

    def system_menu_eq2_gain(self, arg):
        value = self.audiocard.get_volume_parameter(self.audiocard.EQ_2)
        self.lcd.draw_audio_parameter_dialog("Low-Mid Band Gain", self.audiocard.EQ_2, value,
                                             -10.50, 12, self.audio_parameter_commit)

    def system_menu_eq3_gain(self, arg):
        value = self.audiocard.get_volume_parameter(self.audiocard.EQ_3)
        self.lcd.draw_audio_parameter_dialog("Mid Band Gain", self.audiocard.EQ_3, value,
                                             -10.50, 12, self.audio_parameter_commit)

    def system_menu_eq4_gain(self, arg):
        value = self.audiocard.get_volume_parameter(self.audiocard.EQ_4)
        self.lcd.draw_audio_parameter_dialog("High-Mid Band Gain", self.audiocard.EQ_4, value,
                                             -10.50, 12, self.audio_parameter_commit)

    def system_menu_eq5_gain(self, arg):
        value = self.audiocard.get_volume_parameter(self.audiocard.EQ_5)
        self.lcd.draw_audio_parameter_dialog("High Band Gain", self.audiocard.EQ_5, value,
                                             -10.50, 12, self.audio_parameter_commit)

    def audio_parameter_commit(self, symbol, value):
        self.audiocard.set_volume_parameter(symbol, value)

        # special case since VU meters need to recalibrate based on the input gain setting
        if symbol == self.audiocard.CAPTURE_VOLUME:
            self.hardware.recalibrateVU_gain(value)

    def get_callback(self, callback_name):
        return util.DICT_GET(self.callbacks, callback_name)

    def set_mod_tap_tempo(self, bpm):
        try:
            resp = None
            if bpm is not None:
                url = self.root_uri + "set_bpm"
                resp = req.post(url, json={"value": bpm})
            if resp.status_code != 200:
                logging.error("Bad Rest request: %s status: %d" % (url, resp.status_code))
            else:
                logging.debug("BPM changed to: %d" % bpm)
        except:
            logging.debug("status: %s" % resp.status_code)
            return resp.status_code

    def get_bpm(self):
        url = self.root_uri + "get_bpm"
        try:
            resp = req.get(url)
        except:
            logging.debug("status: %s" % resp.status_code)
            return 0

        if resp.status_code != 200:
            logging.error("Cannot connect to mod-host.  Status: %s" % resp.status_code)
            return 0

        return float(resp.text)

    def toggle_tap_tempo_enable(self, *argv):
        self.hardware.toggle_tap_tempo_enable(self.get_bpm())
        self.lcd.update_footswitches()
