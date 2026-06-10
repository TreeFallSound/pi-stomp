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
from pistomp.audiocard import Audiocard

import json
import logging
import os
import requests as req
from requests import Response
import subprocess
import sys
import yaml
from typing import Any

from typing import cast, Any

import common.token as Token
import common.util as util
import modalapi.pedalboard as Pedalboard
import modalapi.wifi as Wifi
from pistomp.lcd320x240 import Lcd
from pistomp.hardware import Controller, Hardware
import pistomp.settings as Settings
from blend.snapshot import SnapshotManager
from modalapi.websocket_bridge import AsyncWebSocketBridge
from modalapi.ws_protocol import parse_message, LoadingEndMessage, PedalSnapshotMessage, PluginBypassMessage, AddPluginMessage, ParamSetMessage, WebSocketMessage
from modalapi.pedalboard_monitor import FileChangeMonitor, read_pedalboard_bundle

from pistomp.analogmidicontrol import AnalogMidiControl
from pistomp.encodermidicontrol import EncoderMidiControl
from pistomp.footswitch import Footswitch
from pistomp.tuner import TunerEngine, TunerPanel, TunerSourceFactory
from pistomp.tuner.source import AudioSource, build_source
from pathlib import Path


class Modhandler(Handler):
    __single = None

    def __init__(self, audiocard: Audiocard, homedir, data_dir="/home/pistomp/data"):
        logging.info("Init modhandler")
        if Modhandler.__single:
            raise RuntimeError("Attempt to create second Modhandler singleton", Modhandler.__single)
        Modhandler.__single = self

        self.audiocard = audiocard

        self.homedir = homedir
        self.username = "pistomp"
        self.root_uri = "http://localhost:80/"
        self.settings = Settings.Settings()
        self.software_version = None
        self.build_version = "User build"
        self.build_file = "/home/pistomp/.osbuild"

        self.pedalboards = {}
        self.pedalboard_list = []  # TODO LAME to have two lists
        self.plugin_dict = {}

        self.wifi_status = {}
        self.eq_status = {}
        self.SystemState = "unknown"
        self.throttled = "unknown"
        self.temperature = "unknown"
        self.bypass_left = False
        self.bypass_right = False

        self.current: Modhandler.Current | None = None
        self._lcd: Lcd | None = None
        self._hardware: Hardware | None = None

        # Stores snapshot index from loading_end until pedalboard change is detected
        self.next_pedalboard_preset_index = None

        # Backup
        self.backup_dir = "/media/usb0/backups"
        self.backup_file = "pistomp_backup.zip"
        self.data_dir = data_dir

        # Banks
        self.banks_file = os.path.join(self.data_dir, "banks.json")
        self.banks = {}
        self.current_bank = None

        self.last_json_monitor = FileChangeMonitor(os.path.join(self.data_dir, "last.json"))
        self.banks_monitor = FileChangeMonitor(self.banks_file)

        self.wifi_manager = Wifi.WifiManager(on_status_change=self._on_wifi_status_change)

        # WebSocket bridge for MOD-UI communication
        self.ws_bridge = AsyncWebSocketBridge(
            ws_url='ws://localhost:80/websocket',
            backpressure_threshold=8192  # 8 KB
        )
        self.ws_bridge.start()
        logging.info("WebSocket bridge started")

        # Tuner state
        self._tuner_engine: TunerEngine | None = None
        self._tuner_panel: TunerPanel | None = None
        self._tuner_source_factory: TunerSourceFactory | None = None
        self._tuner_muted: bool = False

        # Callback function map.  Key is the user specified name, value is function from this handler
        # Used for calling handler callbacks pointed to by names which may be user set in the config file
        self.callbacks = {"set_mod_tap_tempo": self.set_mod_tap_tempo,
                          "next_snapshot": self.preset_incr_and_change,
                          "previous_snapshot": self.preset_decr_and_change,
                          "toggle_bypass": self.system_toggle_bypass,
                          "toggle_tap_tempo_enable": self.toggle_tap_tempo_enable,
                          "toggle_tuner_enable": self.toggle_tuner_enable,
        }

        # Blend mode manager - multiple blend snapshots per pedalboard
        self.blend_modes: dict[str, Any] = {}  # {snapshot_name: BlendMode}
        self.active_blend_mode: Any | None = None  # Currently active blend mode

    def __del__(self):
        logging.info("Handler cleanup")
        if self.wifi_manager:
            del self.wifi_manager
        # ws_bridge.stop() lives in cleanup(), not here — join() in __del__ blows up
        # during interpreter shutdown on Py 3.14. Daemon thread dies with the process.

    def cleanup(self):
        if self._tuner_engine is not None:
            if self._tuner_muted:
                self.audiocard.set_output_muted(False)
            self._tuner_engine.stop()
            self._tuner_engine = None
            self._tuner_panel = None
        if self._lcd is not None:
            self._lcd.cleanup()
        if self._hardware is not None:
            self._hardware.cleanup()
        if self.ws_bridge is not None:
            self.ws_bridge.stop()
            logging.info("WebSocket bridge stopped")

    # Container for dynamic data which is unique to the "current" pedalboard
    # The self.current pointed above will point to this object which gets
    # replaced when a different pedalboard is made current (old Current object
    # gets deleted and a new one added via self.set_current_pedalboard()
    class Current:
        def __init__(self, pedalboard: Pedalboard.Pedalboard):
            self.pedalboard: Pedalboard.Pedalboard = pedalboard
            self.presets: dict[int, str] = {}
            self.preset_index: int = 0  # Assumes pedalboard loads at snapshot 0 (default behavior)
            self.analog_controllers: dict[str, dict[str, Any]] = {}  # { type: (plugin_name, param_name) }

    def _rest_get(self, url: str) -> Response | None:
        try:
            return req.get(url)
        except Exception as e:
            logging.error("REST GET failed: %s %s" % (url, e))
            return None

    def _rest_post(self, url: str, *, json=None, data=None) -> Response | None:
        try:
            return req.post(url, json=json, data=data)
        except Exception as e:
            logging.error("REST POST failed: %s %s" % (url, e))
            return None

    def add_hardware(self, hardware):
        self._hardware = hardware

    def add_lcd(self, lcd):
        self._lcd = lcd

    @property
    def lcd(self):
        assert self._lcd is not None, "LCD has not been initialized"
        return self._lcd

    @property
    def hardware(self):
        assert self._hardware is not None, "Hardware has not been initialized"
        return self._hardware

    def poll_controls(self):
        if self.hardware:
            self.hardware.poll_controls()

    def poll_indicators(self):
        if self.hardware:
            self.hardware.poll_indicators()

    def poll_wifi(self):
        self.wifi_manager.poll()
        if self._lcd is not None and self.lcd.wifi_menu is not None:
            self.lcd.wifi_menu.tick()

    def _on_wifi_status_change(self, status):
        self.wifi_status = status
        if self._lcd is not None:
            self.lcd.update_wifi(status)
            if self.lcd.wifi_menu is not None:
                self.lcd.wifi_menu.notify_status_change()

    def poll_system_info(self):
        # Get the system state from the systemd service
        try:
            output = subprocess.check_output(['systemctl', 'show', '-p', 'SystemState'])
            if output:
                # Parse the output to extract the SystemState value
                # Output format is typically: SystemState=running
                system_state_line = output.decode().strip()
                if '=' in system_state_line:
                    self.SystemState = system_state_line.split('=', 1)[1]
                else:
                    self.SystemState = system_state_line
                logging.debug("System State: %s" % self.SystemState)
        except subprocess.CalledProcessError as e:
            logging.error("Failed to get system state: %s" % e)
            self.SystemState = "unknown"
        except Exception as e:
            logging.error("Unexpected error getting system state: %s" % e)
            self.SystemState = "unknown"

        # Check for throttling
        try:
            output = subprocess.check_output(['vcgencmd', 'get_throttled'])
            if output:
                # Parse the output to extract the throttled value
                # Output format is typically: throttled=0x0
                throttled_line = output.decode().strip()
                if '=' in throttled_line:
                    throttled_value = throttled_line.split('=', 1)[1]
                    self.throttled = throttled_value
                else:
                    self.throttled = throttled_line
                logging.debug("Throttled status: %s" % self.throttled)
        except subprocess.CalledProcessError as e:
            logging.error("Failed to get throttled status: %s" % e)
            self.throttled = "unknown"
        except Exception as e:
            logging.error("Unexpected error getting throttled status: %s" % e)
            self.throttled = "unknown"

        # Check temperature
        try:
            output = subprocess.check_output(['vcgencmd', 'measure_temp'])
            if output:
                # Parse the output to extract the temperature value
                # Output format is typically: temp=45.2'C
                temp_line = output.decode().strip()
                if '=' in temp_line:
                    temp_value = temp_line.split('=', 1)[1]
                    self.temperature = temp_value
                else:
                    self.temperature = temp_line
                logging.debug("Temperature: %s" % self.temperature)
        except subprocess.CalledProcessError as e:
            logging.error("Failed to get temperature: %s" % e)
            self.temperature = "unknown"
        except Exception as e:
            logging.error("Unexpected error getting temperature: %s" % e)
            self.temperature = "unknown"

    def poll_lcd_updates(self):
        if self._lcd is not None:
            self._lcd.update_wifi(self.wifi_status)
            self._lcd.poll_updates()

    @property
    def lcd_poll_divisor(self) -> int:
        # Tick the LCD on every 10 ms main-loop pass (~100 fps) while the
        # tuner panel is mounted. Strobe's worst-case redraw at STRIPE_W=4
        # is ~4.3 ms of SPI, well inside the 10 ms budget; typical ticks
        # are sub-millisecond. Otherwise fall back to the SPI-clock-derived
        # divisor computed by the LCD itself.
        if self._tuner_panel is not None:
            return 1
        return self._lcd.poll_divisor if self._lcd is not None else 8

    def universal_encoder_select(self, direction):
        if self._lcd is not None:
            self._lcd.enc_step(direction)

    def universal_encoder_sw(self, value, obj=None):
        if self._lcd is not None:
            self._lcd.enc_sw(value)

    def _handle_blend_mode_snapshot_change(self, new_snapshot_index: int):
        """
        Handle blend mode activation/deactivation when snapshot changes.

        Args:
            new_snapshot_index: Index of the new snapshot being loaded
        """
        if not self.blend_modes:
            return

        new_snapshot_name = self.current.presets.get(new_snapshot_index)
        logging.debug(f"Snapshot change: index={new_snapshot_index}, name='{new_snapshot_name}', "
                     f"active_blend={self.active_blend_mode.config.get('name') if self.active_blend_mode else None}")

        # Deactivate current blend mode if switching away
        if self.active_blend_mode:
            old_name = self.active_blend_mode.config.get('name')
            if old_name != new_snapshot_name:
                logging.info(f"Deactivating blend mode '{old_name}' (switching to '{new_snapshot_name}')")
                self.active_blend_mode.deactivate()
                self.active_blend_mode = None
                self.lcd.draw_analog_assignments(self.current.analog_controllers)
            else:
                logging.debug(f"Staying on blend mode '{old_name}'")

        # Activate new blend mode if switching to a blend snapshot
        if new_snapshot_name in self.blend_modes:
            logging.info(f"Activating blend mode '{new_snapshot_name}'")
            self.active_blend_mode = self.blend_modes[new_snapshot_name]
            try:
                # Check for snapshot changes immediately before activating
                # to ensure we have the latest stop data (user may have just saved a snapshot)
                self.active_blend_mode.check_for_snapshot_changes()
                self.active_blend_mode.activate()
                self.lcd.draw_analog_assignments(self.current.analog_controllers)
            except Exception as e:
                logging.error(f"Failed to activate blend mode '{new_snapshot_name}': {e}")
                self.active_blend_mode = None
        else:
            logging.debug(f"Snapshot '{new_snapshot_name}' is not a blend snapshot")

    def _handle_ws_message(self, msg: WebSocketMessage):
        """Handle incoming WebSocket message from MOD-UI."""
        if isinstance(msg, LoadingEndMessage):
            logging.debug(f"WebSocket: Pedalboard loading finished, snapshot={msg.snapshot_id}")
            # Sometimes mod-ui sends us -1 for preset index, but shows 0 anyway ("Default")
            self.next_pedalboard_preset_index = max(0, msg.snapshot_id)

        elif isinstance(msg, PedalSnapshotMessage):
            if self.next_pedalboard_preset_index is not None:
                # Check if we're still on the same pedalboard (stale flag from previous load)
                mod_bundle = read_pedalboard_bundle(self.last_json_monitor.path)
                if mod_bundle and self.current and mod_bundle == self.current.pedalboard.bundle:
                    # Same pedalboard - this is a new snapshot on current board, not a pre-switch
                    logging.debug(f"WebSocket: Snapshot changed to {msg.snapshot_id} ({msg.snapshot_name}) - clearing stale pre-switch flag")
                    self.next_pedalboard_preset_index = None

                    if msg.snapshot_id not in self.current.presets:
                        self.current.presets[msg.snapshot_id] = msg.snapshot_name

                    self.current.preset_index = msg.snapshot_id
                    self._handle_blend_mode_snapshot_change(msg.snapshot_id)
                    self.lcd.draw_title()
                else:
                    # Different pedalboard pending - this is a legitimate pre-switch update
                    logging.debug(f"WebSocket: Pre-switch snapshot changed to {msg.snapshot_id}")
                    self.next_pedalboard_preset_index = msg.snapshot_id
            else:
                assert self.current is not None, "Received snapshot message but no current pedalboard is set"
                logging.debug(f"WebSocket: Snapshot changed to {msg.snapshot_id} ({msg.snapshot_name})")

                if msg.snapshot_id not in self.current.presets:
                    self.current.presets[msg.snapshot_id] = msg.snapshot_name

                self.current.preset_index = msg.snapshot_id
                self._handle_blend_mode_snapshot_change(msg.snapshot_id)
                self.lcd.draw_title()

        elif isinstance(msg, (PluginBypassMessage, AddPluginMessage)):
            # PluginBypassMessage: live delta. AddPluginMessage: (re)connect dump
            if self.current is not None:
                for plugin in self.current.pedalboard.plugins:
                    if plugin.instance_id == msg.instance:
                        logging.debug(f"WebSocket: Plugin {msg.instance} bypass -> {msg.bypassed}")
                        plugin.set_bypass(msg.bypassed)
                        self.lcd.refresh_plugins()
                        break

        elif isinstance(msg, ParamSetMessage):
            # Keep the cached value fresh so a later long-press edit opens at the
            # current value. Not drawn anywhere live, so no LCD refresh.
            if self.current is not None:
                for plugin in self.current.pedalboard.plugins:
                    if plugin.instance_id == msg.instance:
                        param = plugin.parameters.get(msg.symbol)
                        if param is not None:
                            param.value = msg.value
                        break

    def poll_ws_messages(self):
        """Drain inbound WS messages (fast ~10ms cadence). Main-thread only.
        Must not touch next_pedalboard_preset_index (owned by the file-watch path)."""
        for msg in self.ws_bridge.get_received_messages():
            try:
                self._handle_ws_message(parse_message(msg))
            except Exception as e:
                logging.error(f"Error handling WebSocket message '{msg}': {e}")

    def poll_modui_changes(self):
        """Poll for changes from MOD-UI: websockets and file watching"""
        # Drain WS first so loading_end/snapshot lands before the file-watch
        # reads next_pedalboard_preset_index this tick. No-op if already drained.
        self.poll_ws_messages()

        # Check for pedalboard change via last.json
        if self.last_json_monitor.check_for_change():
            self.lcd.draw_info_message("Loading...")
            mod_bundle = read_pedalboard_bundle(self.last_json_monitor.path)
            if mod_bundle and self.current and mod_bundle != self.current.pedalboard.bundle:
                logging.info(f"Pedalboard changed via MOD from: {self.current.pedalboard.bundle} to: {mod_bundle}")

                if mod_bundle not in self.pedalboards:
                    self.load_pedalboards()

                pb = self.reload_pedalboard(mod_bundle)
                self.set_current_pedalboard(pb)
            elif mod_bundle and self.current and self.next_pedalboard_preset_index is not None:
                # Same pedalboard reloaded with a pending snapshot - apply it now
                logging.info(f"Applying pending snapshot {self.next_pedalboard_preset_index} to current pedalboard")
                self.current.preset_index = self.next_pedalboard_preset_index
                self._handle_blend_mode_snapshot_change(self.next_pedalboard_preset_index)
                self.next_pedalboard_preset_index = None
                self.lcd.draw_title()

        # Look for a change in banks file
        if self.banks_monitor.check_for_change():
            logging.info("Reloading banks file: %s" % self.banks_file)
            self.load_banks()

        # Check for snapshot file modifications (blend mode stop edits)
        # Check ALL blend modes, not just active one (user might be editing a stop snapshot)
        for blend_mode in self.blend_modes.values():
            try:
                blend_mode.check_for_snapshot_changes()
            except Exception as e:
                logging.error(f"Blend mode snapshot check failed: {e}")
                # If it's the active one, deactivate it
                if blend_mode == self.active_blend_mode:
                    blend_mode.cleanup()
                    self.active_blend_mode = None

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
                    pbs = util.DICT_GET(bd, 'pedalboards') or {}
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

    def set_lcd_speed(self, speed_mhz):
        self.settings.set_setting('lcd.spi_speed_mhz', speed_mhz)
        self.lcd.show_lcd_speed_message(speed_mhz)
        # Exit cleanly - systemd will restart with new LCD speed
        import time
        import sys
        time.sleep(1.5)  # Show message briefly
        sys.exit(0)

    #
    # Pedalboard Stuff
    #
    def load_pedalboards(self):
        url = self.root_uri + "pedalboard/list"

        resp = self._rest_get(url)
        if resp is None or resp.status_code != 200:
            logging.error("Cannot connect to mod-host")
            sys.exit()

        pbs = json.loads(resp.text)
        for pb in pbs:
            logging.info("Loading pedalboard info: %s" % pb[Token.TITLE])
            bundle = pb[Token.BUNDLE]
            title = pb[Token.TITLE]
            pedalboard = Pedalboard.Pedalboard(title, bundle, root_uri=self.root_uri)
            pedalboard.load_bundle(bundle, self.plugin_dict)
            self.pedalboards[bundle] = pedalboard
            self.pedalboard_list.append(pedalboard)
            #logging.debug("dump: %s" % pedalboard.to_json())

    def reload_pedalboard(self, bundle):
        # find the current pedalboard object associated with that bundle
        old = self.pedalboards[bundle]
        title = old.title

        # create a new one
        pedalboard = Pedalboard.Pedalboard(title, bundle, root_uri=self.root_uri)
        pedalboard.load_bundle(bundle, self.plugin_dict)
        self.pedalboards[bundle] = pedalboard

        # replace the pedalboard in pedalboard_list with the new one
        try:
            index = self.pedalboard_list.index(old)
        except Exception:
            logging.error("Cannot locate pedalboard: %s", title)
        else:
            self.pedalboard_list[index] = pedalboard
        del old

        return pedalboard

    def get_current_pedalboard_bundle_path(self):
        return read_pedalboard_bundle(self.last_json_monitor.path)

    def set_current_pedalboard(self, pedalboard):
        # Cleanup all previous blend modes if active
        for blend_mode in self.blend_modes.values():
            blend_mode.cleanup()
        self.blend_modes = {}
        self.active_blend_mode = None

        # Delete previous "current"
        del self.current

        # Create a new "current"
        self.current = self.Current(pedalboard)

        if self.next_pedalboard_preset_index is not None:
            self.current.preset_index = self.next_pedalboard_preset_index
            self.next_pedalboard_preset_index = None

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
        self.lcd.update_wifi(self.wifi_status)

        # Prepare blend modes if configured (snapshot-based activation)
        try:
            blend_configs = cfg.get('blend_snapshots', []) if cfg else []
            bundle_path = Path(self.current.pedalboard.bundle)

            # Sync all blend snapshots (create/recreate based on config)
            snapshot_indices = SnapshotManager.sync_blend_snapshots(
                bundle_path,
                blend_configs,
                self.root_uri
            )

            # Create and prepare BlendMode instances for each blend snapshot
            from blend import BlendMode
            for blend_cfg in blend_configs:
                snapshot_name = blend_cfg.get('name')
                if not snapshot_name:
                    continue

                blend_mode = BlendMode(self, blend_cfg)
                blend_mode.prepare()  # One-time setup: compute diff maps, create controllers
                self.blend_modes[snapshot_name] = blend_mode
                logging.info(f"Prepared blend mode: '{snapshot_name}'")

            # Auto-switch to FIRST blend snapshot if any exist
            if self.blend_modes:
                first_snapshot_name = list(self.blend_modes.keys())[0]
                first_snapshot_idx = snapshot_indices.get(first_snapshot_name)

                if first_snapshot_idx is not None:
                    logging.info(f"Auto-switching to first blend snapshot: '{first_snapshot_name}' (index {first_snapshot_idx})")
                    self.preset_change(first_snapshot_idx)
                    # Note: preset_change calls _handle_blend_mode_snapshot_change which activates the blend mode

        except Exception as e:
            logging.error(f"Failed to prepare blend modes: {e}")
            self.blend_modes = {}
            self.active_blend_mode = None

    def bind_current_pedalboard(self):
        # "current" being the pedalboard mod-host says is current
        # The pedalboard data has already been loaded, but this will overlay
        # any real time settings
        footswitch_plugins = []
        if self.current:
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
                            controller.parameter = param  # pyright: ignore[reportAttributeAccessIssue]
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

        resp1 = self._rest_get(self.root_uri + "reset")
        if resp1 is None or resp1.status_code != 200:
            logging.error("Bad Reset request")

        uri = self.root_uri + "pedalboard/load_bundle/"

        if pedalboard is None:
            pedalboard = self.pedalboard_list[0]
        #self.set_current_pedalboard(pedalboard)  # TODO is this necessary?
        bundlepath = pedalboard.bundle
        data = {"bundlepath": bundlepath}
        resp2 = self._rest_post(uri, data=data)
        if resp2 is None or resp2.status_code != 200:
            logging.error("Bad Rest request: %s %s" % (uri, data))

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

    def load_current_presets(self) -> None:
        url = self.root_uri + "snapshot/list"
        resp = self._rest_get(url)
        if resp is None or resp.status_code != 200:
            return

        if not self.current:
            logging.error("Cannot load presets since current pedalboard is not set")
            return

        dict = json.loads(resp.text)
        for key, name in dict.items():
            if key.isdigit():
                index = int(key)
                self.current.presets[index] = name

        # Get current snapshot (preset) info
        url = self.root_uri + "snapshot/name?id=current"  # this will fail (500) for non pi-stomp versions of mod-ui
        resp = self._rest_get(url)
        if resp is None:
            return

        if resp.status_code == 200 and resp.text is not None:
            current_snapshot_name = cast(str, util.DICT_GET(json.loads(resp.text), "name"))
            for i, n in self.current.presets.items():
                if n == current_snapshot_name:
                    self.current.preset_index = i
                    break

    def preset_change(self, index):
        if not self.current:
            logging.error("Cannot change preset since current pedalboard is not set")
            return

        logging.info("preset change: %d" % index)

        if index < 0 or index >= len(self.current.presets):
            self.lcd.draw_message_dialog("Snapshot id %d does not exist for this pedalboard" % index)
            return

        # Handle blend mode snapshot-based activation
        self._handle_blend_mode_snapshot_change(index)

        self.lcd.draw_info_message("Loading...")
        url = (self.root_uri + "snapshot/load?id=%d" % index)
        # req.get(self.root_uri + "reset")
        resp = self._rest_get(url)
        if resp is None or resp.status_code != 200:
            logging.error("Bad Rest request: %s" % url)
        self.current.preset_index = index

        # Update name on lcd
        self.lcd.draw_title()
        # Bypass/param changes from the snapshot arrive via the WS drain (source of truth).

    def preset_incr_and_change(self, *argv):
        assert self.current is not None, "Current pedalboard is not set"
        index = self.next_preset_index(self.current.presets, self.current.preset_index, True)
        self.preset_change(index)

    def preset_decr_and_change(self, *argv):
        assert self.current is not None, "Current pedalboard is not set"
        index = self.next_preset_index(self.current.presets, self.current.preset_index, False)
        self.preset_change(index)

    def preset_set_and_change(self, index):
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
            # Non-footswitch plugin: update locally then notify mod-ui.
            # No echo arrives for WS-initiated bypass. Contrast with footswitches,
            # which send MIDI CC → mod-host internally → feedback → msg_callback.
            value = plugin.toggle_bypass()
            self.ws_bridge.send_parameter(plugin.instance_id, ":bypass", value)
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

        # Audio parameter (volume, EQ, etc.) - no REST update needed
        if param.instance_id is None:
            self.audio_parameter_commit(param.symbol, value)
            return

        self.ws_bridge.send_parameter(param.instance_id, param.symbol, param.value)

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
                                              '--work-tree', self.homedir, 'describe',
                                              '--dirty=*', '--always'])
            if output:
                self.software_version = output.decode()
                logging.info("pi-Stomp Software Version: %s" % self.software_version)
        except subprocess.CalledProcessError:
            logging.error("Cannot obtain git software tag info")

        try:
            if Path(self.build_file).exists():
                self.build_version = ""
                with open(self.build_file, 'r') as file:
                    j = json.load(file)
                    build_tag = util.DICT_GET(j, 'build-tag')
                    build_date = util.DICT_GET(j, 'build-date')
                    self.build_version = "{}-{}".format(build_tag, build_date)
            else:
                logging.warning("Build file does not exist: %s" % self.build_file)
        except:
            logging.error("Cannot read build file: %s" % self.build_file)

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
        self.lcd.cleanup()
        logging.info("System Shutdown")
        os.system('sudo systemctl --no-wall poweroff')

    def system_menu_reboot(self, arg):
        self.lcd.splash_show(False)
        logging.info("System Reboot")
        os.system('sudo systemctl reboot')

    def check_usb(self):
        self.usbflash = False
        if not os.path.exists(self.backup_dir):
            os.mkdir(self.backup_dir)
        stat = subprocess.call(["systemctl", "is-active", "--quiet", "usbmount@dev-sda1"])
        if(stat == 0):
            self.usbflash = True
        else:
            self.usbflash = False

    def user_backup_data(self, arg):
        self.check_usb()
        if self.usbflash:
            self.lcd.draw_info_message("Backing up, please wait...", refresh=True)
            logging.info("Data backup...")
            cmd = os.path.join(self.homedir, 'util', 'data-backup.sh')
            try:
                output = subprocess.check_output([cmd, os.path.join(self.backup_dir, self.backup_file), self.data_dir])
                self.lcd.draw_message_dialog("Backup complete", "Info")
                logging.info("Backup complete")
            except subprocess.CalledProcessError as e:
                logging.error("user_backup_data:" + str(e.output))
                return e.output.decode('utf-8')
            finally:
                self.lcd.draw_info_message("", refresh=True)
        else:
            logging.info("No USB device found")
            self.lcd.draw_message_dialog("No USB device found")

    def user_restore_data(self, arg):
        self.check_usb()
        if self.usbflash:
            self.lcd.draw_info_message("Restoring, please wait...", refresh=True)
            logging.info("Restoring data backup...")
            cmd = os.path.join(self.homedir, 'util', 'data-restore.sh')
            try:
                output = subprocess.check_output(['sudo', '-u', self.username, cmd,
                                                  os.path.join(self.backup_dir, self.backup_file), self.data_dir])
                logging.info("Restore complete")
                self.system_menu_restart_sound(None)
            except subprocess.CalledProcessError as e:
                self.lcd.draw_message_dialog(e.output.decode('utf-8'))
                logging.error("user_restore_data: " + e.output.decode('utf-8'))
            finally:
                self.lcd.draw_info_message("", refresh=True)
        else:
            logging.info("No USB device found")
            self.lcd.draw_message_dialog("No USB device found")

    def system_menu_save_current_pb(self, _arg: None):
        if self.current is None:
            logging.error("No current pedalboard set, cannot save")
            self.lcd.draw_message_dialog("No current pedalboard set, cannot save")
            return

        logging.debug("save current")
        # TODO this works to save the pedalboard values, but just default, not Preset values
        # Figure out how to save preset (host.py:preset_save_replace)
        # TODO this also causes a problem if self.current.pedalboard.title != mod-host title
        # which can happen if the pedalboard is changed via MOD UI, not via hardware
        url = self.root_uri + "pedalboard/save"
        resp = self._rest_post(url, data={"asNew": "0", "title": self.current.pedalboard.title})
        if resp is None or resp.status_code != 200:
            logging.error("Bad Rest request: %s" % url)
        else:
            logging.debug("saved")

    def system_menu_update_sample_pedalboards(self):
        logging.debug("update_sample_pedalboards")
        cmd = os.path.join(self.homedir, 'util', 'update-sample-pedalboards.sh')
        try:
            output = subprocess.check_output(['sudo', '-u', self.username, cmd])
            return output.decode('utf-8')
        except subprocess.CalledProcessError as e:
            logging.error("update sample pedalboards:" + str(e.output))
            return e.output.decode('utf-8')

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
        if bpm is not None:
            self.ws_bridge.send_bpm(bpm)

    def get_bpm(self):
        url = self.root_uri + "get_bpm"
        resp = self._rest_get(url)
        if resp is None or resp.status_code != 200:
            return 0.0
        return float(resp.text)

    def toggle_tap_tempo_enable(self, *argv):
        self.hardware.toggle_tap_tempo_enable(self.get_bpm())
        self.lcd.update_footswitches()

    def set_tuner_source_factory(self, factory: TunerSourceFactory) -> None:
        self._tuner_source_factory = factory

    def _tuner_factory(self, port: str) -> AudioSource:
        factory = self._tuner_source_factory or (lambda p, *, name: build_source("jack", p, name=name))
        return factory(port, name=f"pistomp-tuner-{port.split('_')[-1]}")

    def toggle_tuner_enable(self, *argv) -> None:
        if self._tuner_engine is None:
            muted = bool(self.settings.get_setting(Token.TUNER_MUTE))
            input_port = int(self.settings.get_setting(Token.TUNER_INPUT) or 1)
            engine = TunerEngine(self._tuner_factory(f"system:capture_{input_port}"))
            engine.start()
            self._tuner_engine = engine
            if muted:
                self.audiocard.set_output_muted(True)
                self._tuner_muted = True
            panel = TunerPanel(
                engine,
                on_dismiss=self.toggle_tuner_enable,
                on_mute_toggle=self._toggle_tuner_mute,
                on_input_toggle=self._toggle_tuner_input,
                muted=muted,
                input_port=input_port,
            )
            self._tuner_panel = panel
            self.lcd.show_tuner_panel(panel)
        else:
            self._dismiss_tuner()

    def _dismiss_tuner(self) -> None:
        if self._tuner_muted:
            self.audiocard.set_output_muted(False)
            self._tuner_muted = False
        self.lcd.hide_tuner_panel()
        if self._tuner_engine is not None:
            self._tuner_engine.stop()
            self._tuner_engine = None
        self._tuner_panel = None

    def _toggle_tuner_mute(self) -> None:
        new_muted = not self._tuner_muted
        self.audiocard.set_output_muted(new_muted)
        self._tuner_muted = new_muted
        self.settings.set_setting(Token.TUNER_MUTE, new_muted)
        if self._tuner_panel is not None:
            self._tuner_panel.set_muted(new_muted)

    def _toggle_tuner_input(self) -> None:
        current_port = int(self.settings.get_setting(Token.TUNER_INPUT) or 1)
        new_port = 2 if current_port == 1 else 1
        old_engine = self._tuner_engine
        engine = TunerEngine(self._tuner_factory(f"system:capture_{new_port}"))
        engine.start()
        self.settings.set_setting(Token.TUNER_INPUT, new_port)
        if old_engine is not None:
            old_engine.stop()
        self._tuner_engine = engine
        if self._tuner_panel is not None:
            self._tuner_panel.set_engine(engine)
            self._tuner_panel.set_input_port(new_port)
