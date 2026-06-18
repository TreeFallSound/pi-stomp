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
import time
import socket
from typing import Optional
import common.token as Token
import common.parameter as Parameter
from ui.ethernet_menu import EthernetMenu
from ui.wifi_menu import WifiMenu
import pistomp.category as Category
import pistomp.lcd as abstract_lcd
import pistomp.switchstate as switchstate
import pygame

from uilib import *
from uilib.gridpanel import GridPanel
from uilib.pygame_init import font as _make_font
from uilib.lcd_ili9341 import *
from modalapi.layout import build_layout_compress

from pistomp.footswitch import Footswitch  # TODO would like to avoid this module knowing such details
from pistomp.analogmidicontrol import AnalogMidiControl, as_midi_value
from pistomp.encoder_controller import EncoderController
from blend.manager import BlendMode
from pistomp.tuner.panel import TunerPanel
from plugins.base import PluginPanel
from plugins import PANELS

# Parameter dialog auto-dismiss timeout (seconds)
PARAMETER_DIALOG_TIMEOUT = 1.0

class Lcd(abstract_lcd.Lcd):
    CAPTURE_SOCKET_PATH = "/tmp/pistomp-lcd.sock"

    def __init__(self, cwd, handler=None, flip=False, display=None, spi_speed_mhz=24):
        self.cwd = cwd
        self.imagedir = os.path.join(cwd, "images")
        Config(os.path.join(cwd, 'ui', 'config.json'))
        self.handler = handler
        self.flip = flip
        self.spi_speed_mhz = spi_speed_mhz

        self._capture_socket = None
        self._capture_check_tick = 0

        # Calculate optimal polling divisor based on LCD speed
        # 24MHz: 78ms/frame → poll every 80ms (divisor=8)
        # 48MHz: 39ms/frame → poll every 40ms (divisor=4)
        # 56MHz: 34ms/frame → poll every 30ms (divisor=3)
        frame_time_ms = (56.0 / spi_speed_mhz) * 33.6
        self.poll_divisor = max(1, round(frame_time_ms / 10.0))

        # TODO would be good to decouple the actual LCD hardware.  This file should work for any 320x240 display
        if display is None:
            import board
            import digitalio
            display = LcdIli9341(board.SPI(),
                                 digitalio.DigitalInOut(board.CE0),
                                 digitalio.DigitalInOut(board.D6),
                                 digitalio.DigitalInOut(board.D5),
                                 spi_speed_mhz * 1_000_000,
                                 flip)

        # Colors
        self.background = (0, 0, 0)
        self.foreground = (255, 255, 255)
        self.color_splash_up = (70, 255, 70)
        self.color_splash_down = (255, 20, 20)
        self.default_plugin_color = "Silver"
        self.category_color_map = {
            'Delay': "MediumVioletRed",
            'Distortion': "Lime",
            'Dynamics': "OrangeRed",
            'Filter': (205, 133, 40),
            'Generator': "Indigo",
            'Midiutility': "Gray",
            'Modulator': (50, 50, 255),
            'Reverb': (20, 160, 255),
            'Simulator': "SaddleBrown",
            'Spacial': "Gray",
            'Spectral': "Red",
            'Utility': "Gray"
        }

        # TODO get fonts from config.json
        from pathlib import Path
        _fonts_dir = Path(__file__).resolve().parent.parent / "fonts"
        self.title_font = _make_font(_fonts_dir / "DejaVuSans-Bold.ttf", 26)
        self.splash_font = _make_font(_fonts_dir / "DejaVuSans.ttf", 48)
        self.small_font = _make_font(_fonts_dir / "DejaVuSans.ttf", 20)
        self.tiny_font = _make_font(_fonts_dir / "DejaVuSans.ttf", 16)
        self.title_split_orig = 190
        self.title_split = self.title_split_orig
        self.display_width = 320
        self.display_height = 240
        self.plugin_width = 78
        self.plugin_height = 29
        self.plugin_label_length = 7
        self.footswitch_height = 32
        self.footswitch_width = 80
        # space between footswitch icons where index is the footswitch count
        #                                0    1    2    3    4   5   6   7
        self.footswitch_pitch_options = [120, 120, 120, 128, 80, 65, 65, 65]
        self.footswitch_pitch = None

        # widgets
        self.w_wifi = None
        self._wifi_frames: list[pygame.Surface] = [
            load_surface(os.path.join(self.imagedir, f'wifi_processing_{i}.png'))
            for i in range(1, 4)
        ]
        self._wifi_tick = 0
        self._wifi_ticks_per_frame = 2
        self.wifi_menu: Optional[WifiMenu] = None
        self.ethernet_menu: EthernetMenu = EthernetMenu(self)
        self.w_eq = None
        self.w_power = None
        self.w_wrench = None
        self.w_pedalboard = None
        self.w_colon = None
        self.w_preset = None
        self.w_plugins = []
        self.grid_panel: Optional[GridPanel] = None
        self._fullscreen_panel = None
        self.w_footswitches = []
        self.w_controls = []
        self.w_splash = None
        self.w_info_msg = None
        self.w_parameter_dialogs = {}

        # panels
        self.pstack = PanelStack(display, image_format='RGB', use_dimming=True)
        self.splash_panel = Panel(box=Box.xywh(0, 0, self.display_width, self.display_height))
        self.pstack.push_panel(self.splash_panel, refresh=False)
        self.main_panel = Panel(box=Box.xywh(0, 0, self.display_width, self.display_height))
        self.main_panel_pushed = False
        self.footswitch_panel = ShroudedPanel(box=Box.xywh(0, self.display_height - self.footswitch_height,
                                                            self.display_width, self.footswitch_height),
                                              shroud_alpha=224, no_dim=True, accepts_input=False)
        self._fullscreen_panel: Panel | None = None
        self._tuner_panel = None

        self.pedalboards = {}

        self.wifi_menu = WifiMenu(self)

        if not display.has_system_splash:
            self.splash_show(True)

    #
    # Navigation
    #

    def enc_step_widget(self, widget, direction):
        # TODO check if widget is type
        if direction == 0:
            return
        event = InputEvent.RIGHT if direction > 0 else InputEvent.LEFT
        for _ in range(abs(direction)):
            widget.input_event(event)

    def enc_step(self, d):
        if d == 0:
            return
        event = InputEvent.RIGHT if d > 0 else InputEvent.LEFT
        for _ in range(abs(d)):
            self.pstack.input_event(event)

    def enc_sw(self, v):
        if v == switchstate.Value.RELEASED:
            return self.pstack.input_event(InputEvent.CLICK)
        elif v == switchstate.Value.LONGPRESSED:
            return self.pstack.input_event(InputEvent.LONG_CLICK)
        return False

    #
    # Main
    #
    def link_data(self, pedalboards, current, footswitches):
        self.pedalboards = pedalboards
        self.current = current
        self.footswitches = footswitches

    def draw_main_panel(self):
        self.draw_tools(None, None, None, None)
        self.main_panel.sel_widget(self.w_wrench)  # Make the System tool (wrench) the initial selected item
        self.draw_title()
        self.draw_analog_assignments(self.current.analog_controllers)
        self.draw_plugins()
        self.draw_footswitches()
        if self.footswitch_panel in self.main_panel.sel_list:
            self.main_panel.sel_list.remove(self.footswitch_panel)
        self.main_panel.add_sel_widget(self.footswitch_panel)
        if self.footswitch_panel.sel_ref is not None:
            self.footswitch_panel.sel_ref.set_selected(False)
        self.footswitch_panel.sel_ref = None
        if not self.main_panel_pushed:
            self.pstack.push_panel(self.main_panel, refresh=False)
            self.pstack.push_panel(self.footswitch_panel, refresh=False)
            self.main_panel_pushed = True
            self.pstack.refresh()
        #self.main_panel.refresh()

    def handle(self, event: ControllerEvent) -> bool:
        # When a fullscreen panel is top-most and is an InputSink, ask it first.
        # It returns True to stop the event from reaching the normal handler cascade.
        if self._fullscreen_panel is not None and self.pstack.current is self._fullscreen_panel:
            if self._fullscreen_panel.handle(event):
                return True
        return False

    def poll_updates(self):
        for d in self.w_parameter_dialogs.values():
            d.tick()
        if self.w_pedalboard is not None:
            self.w_pedalboard.tick()
        if self.w_preset is not None:
            self.w_preset.tick()

        self.pstack.poll_updates()
        if self._fullscreen_panel is not None and self.pstack.current is self._fullscreen_panel:
            self._fullscreen_panel.tick()
        if self._tuner_panel is not None and self.pstack.current == self._tuner_panel:
            self._tuner_panel.tick()
        self._poll_capture_socket()

        # Update control progress bars (analog controls and encoders)
        if self.pstack.current == self.main_panel:
            for icon in self.w_controls:
                if icon.object is None:
                    continue

                midi_value = None
                if isinstance(icon.object, AnalogMidiControl):
                    midi_value = as_midi_value(icon.object.last_read)
                elif isinstance(icon.object, EncoderController):
                    midi_value = icon.object.midi_value
                elif isinstance(icon.object, BlendMode):
                    input_ctrl = icon.object.input_controller.controlled_input
                    if input_ctrl:
                        position = input_ctrl.get_normalized_value()
                        midi_value = int(position * 127)

                        stops = icon.object.input_controller.stops
                        closest_stop = min(stops, key=lambda s: abs(s.position - position))
                        snapshot_name = self.handler.current.presets.get(closest_stop.snapshot_index, "")
                        if snapshot_name and snapshot_name != icon.text:
                            icon.set_text(snapshot_name)
                    else:
                        logging.warning("BlendMode icon has no associated input controller")

                if midi_value is not None:
                    progress = midi_value / 127.0
                    if icon.progress != progress:
                        icon.set_progress(progress)

    def _poll_capture_socket(self):
        self._capture_check_tick += 1
        if self._capture_socket is None:
            # Check for socket existence every ~2 seconds (assuming 10-20ms poll rate)
            if self._capture_check_tick % 100 == 0:
                if os.path.exists(self.CAPTURE_SOCKET_PATH):
                    try:
                        self._capture_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        self._capture_socket.connect(self.CAPTURE_SOCKET_PATH)
                        # Increase buffer size to handle multiple 300KB frames (4MB = ~13 frames)
                        self._capture_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
                        # We don't want to block the main loop if the consumer is slow
                        self._capture_socket.setblocking(False)
                        self.pstack.set_capture_callback(self._send_capture_frame)
                        logging.info("LCD capture connected")
                        # Force a full refresh so the recorder gets a frame immediately
                        self.pstack.refresh()
                    except Exception:
                        if self._capture_socket:
                            self._capture_socket.close()
                        self._capture_socket = None
        elif self._capture_check_tick % 500 == 0:
            # Periodically check if the socket is still valid
            try:
                self._capture_socket.send(b"", socket.MSG_DONTWAIT)
            except (socket.error, BrokenPipeError):
                self._disconnect_capture()

    def _send_capture_frame(self, image):
        if self._capture_socket:
            try:
                # Send raw RGB data. 320x240x3 = 230,400 bytes.
                # Use sendall with non-blocking - if it fails, we drop and disconnect
                self._capture_socket.sendall(image.tobytes())
            except (socket.error, BrokenPipeError, BlockingIOError):
                # BlockingIOError means the recorder can't keep up - we disconnect
                # to avoid slowing down pi-stomp
                logging.warning("LCD capture disconnected or buffer full")
                self._disconnect_capture()

    def _disconnect_capture(self):
        if self._capture_socket:
            try:
                self._capture_socket.close()
            except Exception:
                pass
        self._capture_socket = None
        self.pstack.set_capture_callback(None)
        logging.info("LCD capture disabled")

    def show_tuner_panel(self, panel: TunerPanel) -> None:
        self._tuner_panel = panel
        self.pstack.push_panel(panel)
        # push_panel composes the (still-blank) panel onto the stack but
        # doesn't draw the panel's children. Force a full redraw so bg, rules,
        # header and hint are on screen before tick()'s partial refreshes start.
        panel.refresh()

    def show_plugin_panel(self, panel: Panel) -> None:
        self._fullscreen_panel = panel
        self.pstack.push_panel(panel)
        panel.refresh()

    def hide_plugin_panel(self) -> None:
        if self._fullscreen_panel is not None:
            self.pstack.pop_panel(self._fullscreen_panel)
        self._fullscreen_panel = None

    def has_active_fullscreen_panel(self) -> bool:
        return self._fullscreen_panel is not None

    @property
    def plugin_panel(self) -> PluginPanel | None:
        return self._fullscreen_panel if isinstance(self._fullscreen_panel, PluginPanel) else None

    #
    # Toolbar
    #

    # Toolbar
    #
    def draw_tools(self, wifi_type=None, eq_type=None, bypass_type=None, system_type=None):
        if self.w_wifi is not None:
            return
        self.w_wifi = ImageWidget(
            box=Box.xywh(210, 0, 20, 20),
            image=os.path.join(self.imagedir, 'wifi_gray.png'),
            parent=self.main_panel,
            action=self.wifi_menu.open,
        )
        self.main_panel.add_sel_widget(self.w_wifi)
        if self.w_eq is not None:
            return
        self.w_eq = ImageWidget(box=Box.xywh(240, 0, 20, 20), image=os.path.join(self.imagedir,
                                  'eq_blue.png'), parent=self.main_panel, action=self.draw_audio_menu)
        self.main_panel.add_sel_widget(self.w_eq)
        self.w_power = ImageWidget(box=Box.xywh(270, 0, 20, 20), image=os.path.join(self.imagedir,
                                   'power_gray.png'), parent=self.main_panel, action=self.toggle_bypass)
        self.main_panel.add_sel_widget(self.w_power)
        self.w_wrench = ImageWidget(box=Box.xywh(296, 0, 20, 20), image=os.path.join(self.imagedir,
                             'wrench_silver.png'), parent=self.main_panel, action=self.draw_system_menu)
        self.main_panel.add_sel_widget(self.w_wrench)

    def toggle_bypass(self, event, widget):
        if event == InputEvent.CLICK:
            self.handler.system_toggle_bypass()
        elif event == InputEvent.LONG_CLICK:
            self.draw_bypass_preference()

    def draw_bypass_preference(self):
        pref = self.handler.settings.get_setting(Token.BYPASS)
        items = [("Left",  self.handler.change_bypass_preference, Token.LEFT, pref == Token.LEFT),
                 ("Right", self.handler.change_bypass_preference, Token.RIGHT, pref == Token.RIGHT),
                 ("Left & Right",  self.handler.change_bypass_preference, Token.LEFT_RIGHT,
                  pref == Token.LEFT_RIGHT or pref == None)]
        self.draw_selection_menu(items, "Bypass Preference", auto_dismiss=True)

    #
    # Title (Pedalboard and Preset)
    #
    def draw_title(self):
        self.draw_pedalboard(self.current.pedalboard.title)
        self.draw_preset(self.current.presets[self.current.preset_index])
        self.draw_info_message("")  # clear loading msg
        self.main_panel.refresh()

    def draw_pedalboard(self, pedalboard_name):
        text_width = get_text_size(pedalboard_name, self.title_font)[0]
        spacing = 2  # Default sel_width for selectable widgets
        min_box_width = text_width + (spacing * 2)
        self.title_split = min(min_box_width, self.title_split_orig)

        if self.w_pedalboard is not None:
            self.w_pedalboard.set_text(pedalboard_name)
            self.w_pedalboard.set_box(box=Box.xywh(0, 20, self.title_split, 36), realign=True, refresh=True)
        else:
            self.w_pedalboard = ScrollingText(
                box=Box.xywh(0, 20, self.title_split, 36),
                text=pedalboard_name,
                font=self.title_font,
                parent=self.main_panel,
                action=self.draw_pedalboard_menu,
                lcd_poll_divisor=self.poll_divisor,
            )
            self.main_panel.add_sel_widget(self.w_pedalboard)

        colon_width = get_text_size(":", self.title_font)[0]
        colon_x = self.title_split + spacing
        if self.w_colon is not None:
            self.w_colon.set_box(box=Box.xywh(colon_x, 20, colon_width, 36), realign=True, refresh=True)
        else:
            self.w_colon = TextWidget(
                box=Box.xywh(colon_x, 20, colon_width, 36),
                text=":",
                font=self.title_font,
                h_margin=0,
                parent=self.main_panel,
            )

    def draw_preset(self, preset_name):
        colon_width = get_text_size(":", self.title_font)[0]
        padding = 2  # Must match padding in draw_pedalboard
        x = self.title_split + padding + colon_width + padding
        width = self.display_width - x
        if self.w_preset is not None:
            self.w_preset.set_text(preset_name)
            self.w_preset.set_box(box=Box.xywh(x, 20, width, 36), realign=True, refresh=True)
            return
        self.w_preset = ScrollingText(
            box=Box.xywh(x, 20, width, 36),
            text=preset_name,
            font=self.title_font,
            parent=self.main_panel,
            action=self.draw_preset_menu,
            lcd_poll_divisor=self.poll_divisor,
        )
        self.main_panel.add_sel_widget(self.w_preset)

    def draw_pedalboard_menu(self, event, widget):
        items = []
        bank_pbs = util.DICT_GET(self.handler.get_banks(), self.handler.get_bank())

        if bank_pbs is None:
            # No bank so display all pedalboards as they're stored (alphabetically)
            for p in self.pedalboards:
                items.append((p.title, self.handler.pedalboard_change, p))
        else:
            # Bank is set so show only those in the bank and in the order defined by the bank
            for b in bank_pbs:
                for p in self.pedalboards:  # LAME ugly O(N2) search
                    if p.title == b:
                        items.append((p.title, self.handler.pedalboard_change, p))

        self.draw_selection_menu(items, "Pedalboards", auto_dismiss=True, dismiss_option=True)

    def draw_preset_menu(self, event, widget):
        items = []
        for (i, name) in self.current.presets.items():
            items.append((name, self.handler.preset_change, i))
        self.draw_selection_menu(items, "Snapshots", auto_dismiss=True, dismiss_option=True)

    def draw_selection_menu(self, items, title="", auto_dismiss=False, dismiss_option=False,
                            font=None, title_font=None, default_item=None):
        # items is a list of tuples: (label, callback, arg) or (label, callback, arg, is_active)
        # or (label, callback, arg, is_active, long_callback) where long_callback is called
        # instead of callback on a long press.
        def menu_action(event, params):
            if event == InputEvent.LONG_CLICK and len(params) >= 5 and params[4] is not None:
                params[4](params[2])
                return
            callback = params[1]
            if callback is None:
                return
            callback(params[2])

        extra = {}
        if font is not None:
            extra['font'] = font
        if title_font is not None:
            extra['title_font'] = title_font
        m = Menu(title=title, items=items, auto_destroy=True, default_item=default_item, max_width=180, max_height=200,
                 auto_dismiss=auto_dismiss, dismiss_option=dismiss_option, action=menu_action, **extra)
        self.pstack.push_panel(m)
        return m

    def draw_message_dialog(self, text, title="Error"):
        d = MessageDialog(self.pstack, text, title=title)
        self.pstack.push_panel(d)

    #
    # Plugins
    #
    def draw_plugins(self):
        # Tear down the previous render. The GridPanel destroys its tile
        # children; the outer panel's sel traversal stops yielding them
        # because GridPanel.sel_children() reads its (now-empty) tile_order.
        for w in self.w_footswitches:
            w.destroy()
        self.w_footswitches = []
        if self.grid_panel is not None:
            self.main_panel.del_sel_widget(self.grid_panel)
            self.grid_panel.destroy()
            self.grid_panel = None
        self.w_plugins = []
        if self.plugin_panel is not None:
            self.plugin_panel.destroy()
            self._fullscreen_panel = None

        plugins = self.current.pedalboard.plugins
        plugins_by_id = {p.instance_id.lstrip("/"): p for p in plugins}
        layout = build_layout_compress(plugins_by_id.keys(), self.current.pedalboard.connections)

        def tile_factory(node, box, parent):
            plugin = plugins_by_id[node.id]
            label = plugin.display_name[:self.plugin_label_length]
            label = label.replace("_", "")
            label = self.shorten_name(label, box.width)
            # parent MUST be passed in ctor: attaching later wipes the
            # explicit colors color_plugin() sets via inherited-attr resolution.
            tile = TextWidget(box=box, text=label, outline_radius=5,
                              parent=parent, action=self.plugin_event, object=plugin)
            tile.set_font(self.small_font)
            self.color_plugin(tile, plugin)
            self.w_plugins.append(tile)
            return tile

        # Grid area: below title (y=78) to bottom of LCD (y=240).
        # footswitch_panel is pushed on top of pstack and renders over this.
        self.grid_panel = GridPanel(
            layout, tile_factory,
            box=Box.xywh(0, 78, self.display_width, self.display_height - 78),
            bottom_inset=self.footswitch_height,
            parent=self.main_panel,
        )
        self.main_panel.add_sel_widget(self.grid_panel)

        # Repaint the grid's backing surface with the final tile colors before main_panel blits it
        self.grid_panel.refresh()

        self.main_panel.refresh()

    def plugin_event(self, event, widget, plugin):
        if event == InputEvent.CLICK:
            self.handler.toggle_plugin_bypass(widget, plugin)
        elif event == InputEvent.LONG_CLICK:
            panel_cls = PANELS.get(plugin.uri)
            if panel_cls is not None:
                self.handler.show_plugin_panel(plugin, panel_cls)
            else:
                self.draw_parameter_menu(plugin)

    def footswitch_event(self, event, widget, footswitch):
        if event == InputEvent.CLICK:
            footswitch._on_switch(switchstate.Value.RELEASED, time.monotonic())
        elif event == InputEvent.LONG_CLICK:
            footswitch._on_switch(switchstate.Value.LONGPRESSED, time.monotonic())


    def color_plugin(self, widget, plugin):
        color = self.get_plugin_color(plugin)
        if plugin.is_bypassed() == True:
            widget.set_outline(1, color)
            widget.set_background(self.background)
            widget.set_foreground(self.foreground)
        else:
            widget.set_outline(1, self.background)
            widget.set_background(color)
            widget.set_foreground(self.background)

    def refresh_plugins(self):
        for w in self.w_plugins:
            plugin = w.object
            self.color_plugin(w, plugin)
        if self.plugin_panel is not None:
            self.plugin_panel.refresh()
        self.main_panel.refresh()

    def refresh_plugin(self, plugin):
        for w in self.w_plugins:
            if w.object is plugin:
                self.color_plugin(w, plugin)
                w.refresh()
                break

    def toggle_plugin(self, widget, plugin):
        self.color_plugin(widget, plugin)
        widget.refresh()

    # Try to map color to a valid displayable color, if not use foreground
    def valid_color(self, color):
        if color is None:
            return self.foreground
        try:
            c = pygame.Color(color)
            return (c.r, c.g, c.b)
        except (ValueError, TypeError):
            logging.error("Cannot convert color name: %s" % color)
            return self.foreground

    # Get the color assigned to the plugin category
    def get_category_color(self, category):
        color = self.default_plugin_color
        if category:
            c = util.DICT_GET(self.category_color_map, category)
            if c:
                color = c if isinstance(c, tuple) else self.valid_color(c)
        return color

    def get_plugin_color(self, plugin):
        if plugin.category:
            return self.get_category_color(plugin.category)
        return self.default_plugin_color

    #
    # Parameter Editing
    #
    def draw_parameter_menu(self, plugin):
        items = []
        for (name, param) in sorted(plugin.parameters.items()):
            if name != Token.COLON_BYPASS:
                items.append((name, self.draw_parameter_dialog, param))
        self.draw_selection_menu(items, "Parameters")

    def draw_parameter_dialog(self, parameter, timeout=None):
        # If we already have an active dialog for the parameter, use it
        d = util.DICT_GET(self.w_parameter_dialogs, parameter.name)
        if d is not None and d.parent is not None:
            return d

        # Create a new dialog
        title = parameter.instance_id + ":" + parameter.name
        current_value = parameter.value
        if parameter.type == Parameter.Type.ENUMERATION:
            items = []
            for (label, value) in parameter.get_enum_value_list():
                item = (label, self.parameter_commit_enum, (parameter, value), value==current_value)
                items.append(item)
            d = self.draw_selection_menu(items, title, auto_dismiss=True)
        elif parameter.type == Parameter.Type.TOGGLED:
            items = [ ("On",  self.parameter_commit_enum, (parameter, 1), current_value==1),
                      ("Off", self.parameter_commit_enum, (parameter, 0), current_value==0)]
            d = self.draw_selection_menu(items, title, auto_dismiss=True)
        else:
            d = Parameterdialog(self.pstack, parameter,
                                width=270, height=130, auto_destroy=True, title=title, timeout=timeout,
                                action=self.parameter_commit, object=parameter)
            self.pstack.push_panel(d)

        self.w_parameter_dialogs[parameter.name] = d
        return d  # return the dialog so the parameter can be modified using the tweak knob

    def parameter_commit(self, parameter, value):
        self.handler.parameter_value_commit(parameter, value)

    def parameter_commit_enum(self, param_value_tuple):
        # (parameter_object, value)
        self.parameter_commit(param_value_tuple[0], param_value_tuple[1])

    #
    # Footswitches
    #
    def footswitch_label(self, footswitch):
        """Label for a footswitch bound to a plugin param: the param name, or the plugin instance for a :bypass binding."""
        param = footswitch.parameter
        if param is None:
            return None
        if param.symbol != ":bypass":  # TODO token
            return param.name
        return self.shorten_name(param.instance_id, self.footswitch_width)

    def draw_footswitches(self):
        # One slot-ordered pass over the physical switches, so selection order is
        # the stable physical order regardless of plugin/pedalboard ordering.
        # Bound switches (parameter set) get a colored, labeled, actionable keycap;
        # unbound slots get a placeholder that only toggles its indicator.
        for fs in sorted(self.footswitches, key=lambda f: f.id):
            x = self.get_footswitch_pitch() * fs.id
            if fs.parameter is not None:
                label = self.footswitch_label(fs)
                fs.set_display_label(label)
                color = self.get_category_color(fs.category)
                action = self.footswitch_event
            else:
                label = fs.get_display_label() or ""
                color = None
                action = None
            p = FootswitchWidget(Box.xywh(x, 0, self.footswitch_width, self.footswitch_height),
                                 fs.id, label, color, not fs.toggled,
                                 parent=self.footswitch_panel, action=action, object=fs)
            self.w_footswitches.append(p)
            self.footswitch_panel.add_sel_widget(p)
        self.footswitch_panel.refresh()

    def update_footswitch(self, footswitch):
        for wfs in self.w_footswitches:
            if wfs.object == footswitch:
                if footswitch.parameter is not None:
                    # Binding may be new (e.g. MIDI learn) — reflect label + color.
                    footswitch.set_display_label(self.footswitch_label(footswitch))
                    wfs.color = self.get_category_color(footswitch.category)
                wfs.toggle(footswitch.toggled == False)
                wfs.label = footswitch.get_display_label() or ""
                wfs.refresh()
                break

    def update_footswitches(self):
        for fs in self.footswitches:
            self.update_footswitch(fs)

    def get_footswitch_pitch(self):
        if self.footswitch_pitch is not None:
            return self.footswitch_pitch
        if self.handler:
            num_fs = self.handler.get_num_footswitches()
            if num_fs <= len(self.footswitch_pitch_options):
                self.footswitch_pitch = self.footswitch_pitch_options[self.handler.get_num_footswitches()]
                return self.footswitch_pitch
        return self.footswitch_pitch_options[-1]

    #
    # System Menu
    #
    def draw_system_menu(self, event, widget):
        items = [("System info", self.draw_system_info_dialog, None),
                 ("Tuner", self._toggle_tuner_from_menu, None),
                 ("System shutdown", self.handler.system_menu_shutdown, None),
                 ("System reboot",  self.handler.system_menu_reboot, None),
                 ("Restart sound engine", self.handler.system_menu_restart_sound, None),
                 ("Bank Select >", self.draw_bank_menu, None),
                 ("Pedalboard Management >", self.draw_pedalboard_mgmt_menu, None),
                 ("LCD Speed >", self.draw_lcd_speed_menu, None)]
        self.draw_selection_menu(items, "System Menu")

    def _toggle_tuner_from_menu(self, arg):
        self.pstack.pop_panel(None)  # dismiss the menu first
        self.handler.toggle_tuner_enable()

    def draw_pedalboard_mgmt_menu(self, arg):
        items = [("Save current pedalboard", self.handler.system_menu_save_current_pb, None),
                 ("Reload pedalboards", self.handler.system_menu_reload, None),
                 ("Update sample pedalboards", self.update_sample_pedalboards, None),
                 ("Backup data", self.handler.user_backup_data, None),
                 ("Restore Backup data", self.handler.user_restore_data, None)]
        self.draw_selection_menu(items, "Pedalboard Management")

    def update_sample_pedalboards(self, arg):
        self.pstack.pop_panel(None)
        self.draw_info_message("updating...")
        self.main_panel.refresh()
        result = self.handler.system_menu_update_sample_pedalboards()
        self.draw_info_message("")
        self.main_panel.refresh()

        # Show update stdout dialog
        d = MessageDialog(self.pstack, str(result), title="Pedalboard Update", width=250, height=140)
        self.pstack.push_panel(d)

    def draw_system_info_dialog(self, arg):
        msg="Software:{}\nBuild:{}\nSystemState:{}\nTemperature:{}\nThrottled:{}".format(
            self.handler.software_version,
            self.handler.build_version,
            self.handler.SystemState,
            self.handler.temperature,
            self.handler.throttled)
        d = MessageDialog(self.pstack, msg, title="System Info", width=300, height=130)
        self.pstack.push_panel(d)

    def draw_lcd_speed_menu(self, event):
        current_speed = self.spi_speed_mhz
        items = [
            ("24 MHz (safe)", self.handler.set_lcd_speed, 24, current_speed==24),
            ("48 MHz (experimental)", self.handler.set_lcd_speed, 48, current_speed==48),
            ("56 MHz (experimental)", self.handler.set_lcd_speed, 56, current_speed==56),
            ("80 MHz (experimental)", self.handler.set_lcd_speed, 80, current_speed==80),
        ]
        self.draw_selection_menu(items, "LCD SPI Speed", auto_dismiss=False)

    def show_lcd_speed_message(self, speed_mhz):
        adc_speed = "240 kHz" if speed_mhz <= 24 else "1 MHz"
        msg = f"LCD: {speed_mhz} MHz / ADC: {adc_speed}\n\nRestarting..."
        d = MessageDialog(self.pstack, msg, title="SPI Speed", width=280, height=140)
        self.pstack.push_panel(d)

    def draw_bank_menu(self, event):
        current_bank = self.handler.get_bank()
        items = [("None (All pedalboards)", self.handler.set_bank, None, current_bank==None)]
        for k,v in self.handler.get_banks().items():
            items.append((k, self.handler.set_bank, k, k==current_bank))
        self.draw_selection_menu(items, "Bank Select", auto_dismiss=True)

    def draw_audio_menu(self, event, widget):
        items = [("Output Volume", self.handler.system_menu_headphone_volume, None),
                 ("Input Gain", self.handler.system_menu_input_gain, None),
                 ("VU Calibration", self.handler.system_menu_vu_calibration, None),
                 ("Global EQ", self.handler.system_toggle_eq, None),
                 ("Low Band Gain", self.handler.system_menu_eq1_gain, None),
                 ("Low-Mid Band Gain", self.handler.system_menu_eq2_gain, None),
                 ("Mid Band Gain", self.handler.system_menu_eq3_gain, None),
                 ("High-Mid Band Gain", self.handler.system_menu_eq4_gain, None),
                 ("High Band Gain", self.handler.system_menu_eq5_gain, None)]
        self.draw_selection_menu(items, "Audio Menu") 

    def draw_audio_parameter_dialog(self, parameter, commit_callback):
        d = util.DICT_GET(self.w_parameter_dialogs, parameter.name)
        if d is not None and d.parent is not None:
            return d

        d = Parameterdialog(self.pstack, parameter,
                            width=270, height=130, auto_destroy=True, title=parameter.name,
                            timeout=PARAMETER_DIALOG_TIMEOUT,
                            action=commit_callback, object=parameter.symbol)
        self.w_parameter_dialogs[parameter.name] = d
        self.pstack.push_panel(d)
        return d

    def display_parameter_value(self, parameter: Parameter.Parameter, value: float) -> None:
        d = self.draw_parameter_dialog(parameter, timeout=PARAMETER_DIALOG_TIMEOUT)
        if d:
            d.update_value(value)

    def draw_vu_calibration_dialog(self, symbol, value, commit_callback):
        if value is None:
            value = 512  # 1024 / 2
        name = "VU Calibration"
        info = {
            Token.NAME: name,
            Token.SYMBOL: symbol,
            Token.RANGES: {Token.MINIMUM: 0, Token.MAXIMUM: 1023}
        }
        param = Parameter.Parameter(info, value, None)
        d = Parameterdialog(self.pstack, param,
                            width=270, height=130, auto_destroy=False, title=name, timeout=PARAMETER_DIALOG_TIMEOUT,
                            action=commit_callback, object=symbol)
        self.pstack.push_panel(d)
        return d

    #
    # General
    #
    def splash_show(self, boot=True):
        self.w_splash = TextWidget(box=Box.xywh(12, 80, self.display_width, self.display_height),
                       text="pi Stomp!", font=self.splash_font, parent=self.splash_panel)
        self.w_splash.set_foreground(self.color_splash_up if boot is True else self.color_splash_down)
        self.splash_panel.refresh()

    def cleanup(self):
        if self.pstack.current is not None:
            self.pstack.pop_panel(None)
        if self.footswitch_panel in self.pstack.stack:
            self.pstack.pop_panel(self.footswitch_panel)
        if self.main_panel_pushed and self.main_panel in self.pstack.stack:
            self.pstack.pop_panel(self.main_panel)
        if self.w_splash is not None:
            self.w_splash.set_foreground(self.color_splash_down)
            self.splash_panel.refresh()

    def clear(self):
        pass

    def erase_all(self):
        pass

    def clear_select(self):
        pass

    # Toolbar
    def update_wifi(self, wifi_status):
        if self.w_wifi is None:
            return
        if self.handler.wifi_manager.queue.pending_op_count() > 0:
            period = self._wifi_ticks_per_frame * len(self._wifi_frames)
            self._wifi_tick = (self._wifi_tick + 1) % period
            idx = self._wifi_tick // self._wifi_ticks_per_frame
            self.w_wifi.replace_img(self._wifi_frames[idx])
        else:
            self._wifi_tick = 0
            self.w_wifi.replace_img(self._resolved_wifi_png(wifi_status))

    def _resolved_wifi_png(self, wifi_status):
        if util.DICT_GET(wifi_status, 'hotspot_active'):
            img = "wifi_orange.png"
        elif util.DICT_GET(wifi_status, 'wifi_connected'):
            img = "wifi_silver.png"
        else:
            img = "wifi_gray.png"
        return os.path.join(self.imagedir, img)

    def update_eq(self, eq_status):
        pass

    def update_bypass(self, bypass_left, bypass_right):
        if self.w_power is None:
            return
        if not bypass_left and not bypass_right:
            img = 'power_green.png'
        elif not bypass_left:
            img = 'power_left.png'
        elif not bypass_right:
            img = 'power_right.png'
        else:
            img = 'power_gray.png'
        image_path = os.path.join(self.imagedir, img)
        self.w_power.replace_img(image_path)

    def draw_tool_select(self, tool_type):
        pass

    # Menu Screens (uses deep_edit image and draw objects)
    
    def menu_show(self, page_title, menu_items):
        pass
    
    def menu_highlight(self, index):
        pass

    # Parameter Value Edit
    
    def draw_value_edit(self, plugin_name, parameter, value):
        pass

    def draw_value_edit_graph(self, parameter, value):
        pass

    # Analog Assignments (Tweak, Expression Pedal, etc.)
    def draw_analog_assignments(self, controllers):
        # Quite a few assumptions here
        # Expression pedal in first position, then 3 knobs (for v3)
        # Should work for more or fewer but won't likely look great on the LCD

        # spacing and scaling of text
        minimum = 4 if self.handler.hardware.version >= 3 else 3
        num = max(minimum, len(controllers) + 1)
        width_per_control = int(round(self.display_width / num))
        text_per_control = width_per_control - 16  # minus height of control icon

        # clean up previous control widgets
        for w in self.w_controls:
            w.destroy()
        self.w_controls = []

        x = 0
        y = 56  # vertical position on screen
        for i in range(0, num):
            k = None
            v = None
            for key, value in controllers.items():
                id = util.DICT_GET(value, Token.ID)
                if id is not None and int(id) == i:
                    k = key
                    v = value
                    break

            # Look up the actual control instance for progress bar tracking
            analog_control = None
            for ac in self.handler.hardware.analog_controls + self.handler.hardware.encoders:
                if hasattr(ac, "id") and ac.id == i and getattr(ac, "type", None) != Token.NAV:
                    analog_control = ac
                    break

            # Substitute BlendMode object if this control is the blend mode input
            icon_object = analog_control
            if (
                analog_control is not None
                and self.handler.active_blend_mode
                and analog_control.id == self.handler.active_blend_mode.config.get("input_id", 0)
            ):
                icon_object = self.handler.active_blend_mode

            if k is None:
                # Non-mapped control
                name = "none"
                control_type = Token.EXPRESSION if i == 0 else Token.KNOB  # HACK cuz we don't know type of unmapped
                color = Category.get_category_color(None)
                text_color = color
            else:
                # Mapped control or Volume
                control_type = util.DICT_GET(v, Token.TYPE)
                if control_type == Token.VOLUME:
                    name = "volume"
                    control_type = Token.KNOB
                    color = self.default_plugin_color
                    text_color = color
                else:
                    port_name = util.DICT_GET(v, 'port_name')
                    if port_name:
                        midi_cc = util.DICT_GET(v, 'midi_cc')
                        name = f"{port_name}:{midi_cc}"
                        name = self.shorten_name(name, text_per_control)
                        color = self.default_plugin_color
                        text_color = (180, 180, 255)  # light blue = external routing
                    else:
                        name = self.shorten_name(k.split(":")[1], text_per_control)
                        color = util.DICT_GET(v, Token.COLOR)
                        if color is None:
                            category = util.DICT_GET(v, Token.CATEGORY)
                            text_color = Category.get_category_color(category)
                            color = self.default_plugin_color
                        else:
                            text_color = color

            blend_initial_progress = None
            if isinstance(icon_object, BlendMode):
                text_color = self.default_plugin_color
                color = self.default_plugin_color
                # Initialize label and progress bar from the current input position.
                input_ctrl = icon_object.input_controller.controlled_input
                if input_ctrl:
                    blend_initial_progress = input_ctrl.get_normalized_value()
                    stops = icon_object.input_controller.stops
                    closest_stop = min(stops, key=lambda s: abs(s.position - blend_initial_progress))
                    snapshot_name = self.handler.current.presets.get(closest_stop.snapshot_index, "")
                    if snapshot_name:
                        name = snapshot_name

            if control_type == Token.KNOB:
                w = Icon(
                    box=Box.xywh(x, y, width_per_control, 20),
                    text=name,
                    text_color=text_color,
                    parent=self.main_panel,
                    outline=0,
                    object=icon_object,
                )
                w.set_foreground(color)
                w.add_knob()
                if blend_initial_progress is not None:
                    w.set_progress(blend_initial_progress)
                self.w_controls.append(w)
            elif control_type == Token.EXPRESSION:
                w = Icon(
                    box=Box.xywh(x, y, width_per_control, 20),
                    text=name,
                    text_color=text_color,
                    parent=self.main_panel,
                    outline=0,
                    object=icon_object,
                )
                w.set_foreground(color)
                w.add_pedal()
                if blend_initial_progress is not None:
                    w.set_progress(blend_initial_progress)
                self.w_controls.append(w)

            x += width_per_control
    
    def draw_info_message(self, text, refresh=False):
        if self.w_info_msg is None:
            self.w_info_msg = TextWidget(box=Box.xywh(0, 0, 0, 0), text='', parent=self.main_panel, outline=0,
                                         sel_width=0)
        else:
            self.w_info_msg.set_text(text)
        if refresh:
            self.main_panel.refresh()

    # Plugins
    
    def draw_plugin_select(self, plugin=None):
        pass

    def draw_bound_plugins(self, plugins, footswitches):
        pass

    def refresh_zone(self, zone_idx):
        pass
    
    def shorten_name(self, name, width):
        text = ""
        for x in name.lower().replace('_', '').replace('/', '').replace(' ', ''):
            test = text + x
            tw, _ = get_text_size(test, self.small_font)
            if tw >= width:
                break
            text = test
        return text
