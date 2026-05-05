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

import board
import digitalio
import logging
import os
import time
import common.token as Token
import modalapi.parameter as Parameter
from modalapi.wifi import parse_nmcli_error
import pistomp.category as Category
import pistomp.lcd as abstract_lcd
import pistomp.switchstate as switchstate
from PIL import ImageColor

from uilib import *
from uilib.lcd_ili9341 import *

from pistomp.footswitch import Footswitch  # TODO would like to avoid this module knowing such details

#import traceback

class Lcd(abstract_lcd.Lcd):

    def __init__(self, cwd, handler=None, flip=False):
        self.cwd = cwd
        self.imagedir = os.path.join(cwd, "images")
        Config(os.path.join(cwd, 'ui', 'config.json'))
        self.handler = handler
        self.flip = flip

        # TODO would be good to decouple the actual LCD hardware.  This file should work for any 320x240 display
        display = LcdIli9341(board.SPI(),
                             digitalio.DigitalInOut(board.CE0),
                             digitalio.DigitalInOut(board.D6),
                             digitalio.DigitalInOut(board.D5),
                             24000000,
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
        self.title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
        self.splash_font = ImageFont.truetype('DejaVuSans.ttf', 48)
        self.small_font = ImageFont.truetype("DejaVuSans.ttf", 20)
        self.tiny_font = ImageFont.truetype("DejaVuSans.ttf", 16)
        self.title_split_orig = 190
        self.title_split = self.title_split_orig
        self.display_width = 320
        self.display_height = 240
        self.plugin_width = 78
        self.plugin_height = 29
        self.plugin_label_length = 7
        self.footswitch_height = 60
        self.footswitch_width = 56
        # space between footswitch icons where index is the footswitch count
        #                                0    1    2    3    4   5   6   7
        self.footswitch_pitch_options = [120, 120, 120, 128, 86, 65, 65, 65]
        self.footswitch_pitch = None
        self.footswitch_slots = {}

        # widgets
        self.w_wifi = None
        self._wifi_networks_menu = None
        self.w_eq = None
        self.w_power = None
        self.w_wrench = None
        self.w_pedalboard = None
        self.w_preset = None
        self.w_plugins = []
        self.w_footswitches = []
        self.w_controls = []
        self.w_splash = None
        self.w_info_msg = None
        self.w_parameter_dialogs = {}

        # panels
        self.pstack = PanelStack(display, image_format='RGB', use_dimming=True)  # TODO use dimming without loosing FS's
        self.splash_panel = Panel(box=Box.xywh(0, 0, self.display_width, self.display_height))
        self.pstack.push_panel(self.splash_panel)
        self.main_panel = Panel(box=Box.xywh(0, 0, self.display_width, 170))
        self.main_panel_pushed = False
        self.footswitch_panel = Panel(box=Box.xywh(0, 176, self.display_width, 64))
        self.pstack.push_panel(self.footswitch_panel)

        self.pedalboards = {}

        self.splash_show(True)

    #
    # Navigation
    #

    def enc_step_widget(self, widget, direction):
        #traceback.print_stack()
        # TODO check if widget is type
        if direction > 0:
            widget.input_event(InputEvent.RIGHT)
        elif direction < 0:
            widget.input_event(InputEvent.LEFT)

    def enc_step(self, d):
        #traceback.print_stack()
        if d > 0:
            self.pstack.input_event(InputEvent.RIGHT)
        elif d < 0:
            self.pstack.input_event(InputEvent.LEFT)

    def enc_sw(self, v):
        if v == switchstate.Value.RELEASED:
            self.pstack.input_event(InputEvent.CLICK)
        elif v == switchstate.Value.LONGPRESSED:
            self.pstack.input_event(InputEvent.LONG_CLICK)

    #
    # Main
    #
    def link_data(self, pedalboards, current, footswitches):
        self.pedalboards = pedalboards
        self.current = current
        self.footswitches = footswitches

    def draw_main_panel(self):
        self.footswitch_slots = {}
        self.draw_tools(None, None, None, None)
        self.main_panel.sel_widget(self.w_wrench)  # Make the System tool (wrench) the initial selected item
        self.draw_title()
        self.draw_analog_assignments(self.current.analog_controllers)
        self.draw_plugins()
        self.draw_unbound_footswitches()
        if not self.main_panel_pushed:
            self.pstack.push_panel(self.main_panel)
            self.main_panel_pushed = True
        #self.main_panel.refresh()

    def poll_updates(self):
        self.pstack.poll_updates()

    #
    # Toolbar
    #
    def draw_tools(self, wifi_type=None, eq_type=None, bypass_type=None, system_type=None):
        if self.w_wifi is not None:
            return
        self.w_wifi = ImageWidget(box=Box.xywh(210, 0, 20, 20), image_path=os.path.join(self.imagedir,
                                  'wifi_gray.png'), parent=self.main_panel, action=self.draw_wifi_menu)
        self.main_panel.add_sel_widget(self.w_wifi)
        if self.w_eq is not None:
            return
        self.w_eq = ImageWidget(box=Box.xywh(240, 0, 20, 20), image_path=os.path.join(self.imagedir,
                                  'eq_blue.png'), parent=self.main_panel, action=self.draw_audio_menu)
        self.main_panel.add_sel_widget(self.w_eq)
        self.w_power = ImageWidget(box=Box.xywh(270, 0, 20, 20), image_path=os.path.join(self.imagedir,
                                   'power_gray.png'), parent=self.main_panel, action=self.toggle_bypass)
        self.main_panel.add_sel_widget(self.w_power)
        self.w_wrench = ImageWidget(box=Box.xywh(296, 0, 20, 20), image_path=os.path.join(self.imagedir,
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

    # ----- WiFi menu -----

    _SIGNAL_FILLED = '\u25ae'  # ▮
    _SIGNAL_EMPTY = '\u25af'   # ▯
    _ACTIVE_GLYPH = '\u2714'   # ✔
    _IN_RANGE_NEARBY_CAP = 5
    _OUT_OF_RANGE_CAP = 2

    @staticmethod
    def _signal_bars(signal):
        levels = max(1, min(4, (signal + 12) // 25))
        return Lcd._SIGNAL_FILLED * levels + Lcd._SIGNAL_EMPTY * (4 - levels)

    @staticmethod
    def _format_age(ts):
        if not ts:
            return None
        age = max(0, int(time.time()) - int(ts))
        if age < 60:
            return "now"
        if age < 3600:
            return "%dm ago" % (age // 60)
        if age < 86400:
            return "%dh ago" % (age // 3600)
        return "%dd ago" % (age // 86400)

    def _network_label(self, row):
        ssid = row['ssid']
        active_marker = (self._ACTIVE_GLYPH + ' ') if row.get('active') else ''
        if row.get('signal') is not None:
            suffix = '  ' + self._signal_bars(row['signal'])
        elif row.get('saved'):
            suffix = '  (saved)'
        else:
            suffix = ''
        if row.get('disambiguator'):
            suffix += '  ' + row['disambiguator']
        return active_marker + ssid + suffix

    def toggle_hotspot(self, arg1):
        self.pstack.pop_panel(None)
        self.draw_info_message("connecting...", refresh=True)
        self.handler.system_toggle_hotspot()
        self.draw_info_message("", refresh=True)

    def draw_wifi_menu(self, event, widget):
        wifi_status = self.handler.wifi_status or {}
        supported = util.DICT_GET(wifi_status, 'wifi_supported')
        hotspot_active = util.DICT_GET(wifi_status, 'hotspot_active')
        active_name = util.DICT_GET(wifi_status, 'connection')

        saved = self.handler.wifi_manager.list_connections()
        saved_by_ssid = {}
        for c in saved:
            saved_by_ssid.setdefault(c['ssid'], []).append(c)

        scanned = []
        if supported and not hotspot_active:
            self.draw_info_message("scanning...", refresh=True)
            scanned = self.handler.wifi_manager.scan_networks()
            self.draw_info_message("", refresh=True)
        scanned_ssids = {n['ssid'] for n in scanned}

        title = self._wifi_menu_title(wifi_status, active_name, saved_by_ssid, scanned)

        rows = []
        # In-range networks first (scanned), promoting active to top.
        in_range = []
        for net in scanned:
            profiles = saved_by_ssid.get(net['ssid'], [])
            saved_profile = self._pick_profile(profiles, active_name)
            row = {
                'ssid': net['ssid'],
                'signal': net['signal'],
                'security': net['security'],
                'saved': bool(saved_profile),
                'profile': saved_profile,
                'active': bool(saved_profile) and saved_profile['name'] == active_name,
            }
            self._maybe_disambiguate(row, profiles)
            in_range.append(row)
        in_range.sort(key=lambda r: (not r['active'], -r['signal']))
        in_range = in_range[:self._IN_RANGE_NEARBY_CAP + (1 if any(r['active'] for r in in_range) else 0)]
        rows.extend(in_range)

        # Saved profiles not visible in scan.
        out_of_range = []
        for ssid, profiles in saved_by_ssid.items():
            if ssid in scanned_ssids:
                continue
            for profile in profiles:
                row = {
                    'ssid': ssid,
                    'signal': None,
                    'security': None,
                    'saved': True,
                    'profile': profile,
                    'active': profile['name'] == active_name,
                }
                self._maybe_disambiguate(row, profiles)
                out_of_range.append(row)
        out_of_range.sort(key=lambda r: -(r['profile']['timestamp'] or 0))
        if len(out_of_range) > self._OUT_OF_RANGE_CAP:
            shown = out_of_range[:self._OUT_OF_RANGE_CAP]
            extras = out_of_range[self._OUT_OF_RANGE_CAP:]
        else:
            shown = out_of_range
            extras = []
        rows.extend(shown)

        items = [(self._network_label(row), self._on_network_tap, row) for row in rows]
        if extras:
            items.append(("More saved...", self._draw_more_saved, extras))
        items.append(("Join other network...", self._draw_join_dialog, None))
        hotspot_label = ("Hotspot Mode  \u25cf" if hotspot_active else "Hotspot Mode  \u25cb")
        items.append((hotspot_label, self.toggle_hotspot, None))

        self._wifi_networks_menu = self.draw_selection_menu(items, title, dismiss_option=True)

    def _wifi_menu_title(self, wifi_status, active_name, saved_by_ssid, scanned):
        if util.DICT_GET(wifi_status, 'hotspot_active'):
            return "WiFi \u00b7 Hotspot"
        if active_name:
            ssid = util.DICT_GET(wifi_status, 'ssid') or active_name
            for net in scanned:
                if net['in_use'] or net['ssid'] == ssid:
                    return "WiFi \u00b7 %s %s" % (ssid, self._signal_bars(net['signal']))
            return "WiFi \u00b7 %s" % ssid
        return "WiFi \u00b7 Disconnected"

    def _pick_profile(self, profiles, active_name):
        if not profiles:
            return None
        for p in profiles:
            if p['name'] == active_name:
                return p
        return max(profiles, key=lambda p: p['timestamp'] or 0)

    def _maybe_disambiguate(self, row, profiles):
        if row.get('saved') and len(profiles) > 1 and row.get('profile'):
            age = self._format_age(row['profile'].get('timestamp'))
            if age:
                row['disambiguator'] = "\u00b7 " + age

    def _on_network_tap(self, row):
        if row.get('saved'):
            self._draw_saved_network_menu(row)
        elif self._is_open_network(row.get('security')):
            self._connect_with_feedback(
                lambda: self.handler.wifi_manager.connect_scanned(row['ssid']),
                row['ssid'])
        else:
            self._prompt_password(row['ssid'],
                lambda psk: self._connect_with_feedback(
                    lambda: self.handler.wifi_manager.connect_scanned(row['ssid'], psk),
                    row['ssid']))

    @staticmethod
    def _is_open_network(security):
        if not security or security == '--':
            return True
        return False

    def _draw_saved_network_menu(self, row):
        profile = row['profile']
        items = []
        if row.get('signal') is not None and not row.get('active'):
            items.append(("Connect", self._connect_saved, row))
        items.append(("Replace password", self._draw_replace_psk_dialog, row))
        items.append(("Forget", self._forget_wifi_network, row))
        self.draw_selection_menu(items, row['ssid'], dismiss_option=True)

    def _draw_more_saved(self, extras):
        items = [(self._network_label(row), self._on_network_tap, row) for row in extras]
        self.draw_selection_menu(items, "Saved Networks", dismiss_option=True)

    def _connect_saved(self, row):
        profile = row['profile']
        self._connect_with_feedback(
            lambda: self.handler.wifi_manager.connect_saved(profile['name']),
            row['ssid'])

    def _connect_with_feedback(self, connect_fn, ssid):
        self.pstack.pop_panel(None)
        self.draw_info_message("connecting to %s..." % ssid, refresh=True)
        err = connect_fn()
        self.draw_info_message("", refresh=True)
        if err is None:
            self.draw_info_message("connected: %s" % ssid, refresh=True)
            return
        d = MessageDialog(self.pstack, parse_nmcli_error(err), title="Couldn't connect")
        self.pstack.push_panel(d)

    def _prompt_password(self, ssid, on_submit):
        d = Dialog(width=240, height=110, auto_destroy=True, title='Password for %s' % ssid)
        pw = TextWidget(box=Box.xywh(0, 0, 200, 0), text='', prompt='Passwd :', parent=d,
                        outline=1, sel_width=3, outline_radius=5,
                        align=WidgetAlign.NONE, name='pw_field',
                        edit_message='Password')
        d.add_sel_widget(pw)
        cancel = TextWidget(box=Box.xywh(0, 60, 0, 0), text='Cancel', parent=d,
                            outline=1, sel_width=3, outline_radius=5,
                            action=lambda x, y: self.pstack.pop_panel(d),
                            align=WidgetAlign.NONE, name='cancel_btn')
        d.add_sel_widget(cancel)

        def submit(event, button):
            psk = pw.text
            if not psk:
                return
            self.pstack.pop_panel(d)
            on_submit(psk)

        ok = TextWidget(box=Box.xywh(80, 60, 0, 0), text='Ok', parent=d,
                        outline=1, sel_width=3, outline_radius=5,
                        action=submit, align=WidgetAlign.NONE, name='ok_btn')
        d.add_sel_widget(ok)
        self.pstack.push_panel(d)
        d.refresh()

    def _draw_replace_psk_dialog(self, row):
        profile = row['profile']
        self._prompt_password(row['ssid'],
            lambda psk: self._connect_with_feedback(
                lambda: self.handler.wifi_manager.replace_psk(profile['name'], psk),
                row['ssid']))

    def _draw_join_dialog(self, _):
        d = Dialog(width=240, height=120, auto_destroy=True, title='Join other network')
        ssid_widget = TextWidget(box=Box.xywh(0, 0, 190, 0), text='', prompt='SSID :', parent=d,
                                 outline=1, sel_width=3, outline_radius=5,
                                 align=WidgetAlign.NONE, name='ssid_field',
                                 edit_message='WiFi SSID')
        d.add_sel_widget(ssid_widget)
        pw_widget = TextWidget(box=Box.xywh(0, 30, 169, 0), text='', prompt='Passwd :', parent=d,
                               outline=1, sel_width=3, outline_radius=5,
                               align=WidgetAlign.NONE, name='pw_field',
                               edit_message='Password')
        d.add_sel_widget(pw_widget)

        cancel = TextWidget(box=Box.xywh(0, 90, 0, 0), text='Cancel', parent=d,
                            outline=1, sel_width=3, outline_radius=5,
                            action=lambda x, y: self.pstack.pop_panel(d),
                            align=WidgetAlign.NONE, name='cancel_btn')
        d.add_sel_widget(cancel)

        def submit(event, button):
            ssid = ssid_widget.text
            psk = pw_widget.text
            if not ssid:
                return
            self.pstack.pop_panel(d)
            self._connect_with_feedback(
                lambda: self.handler.wifi_manager.connect_scanned(ssid, psk or None),
                ssid)

        ok = TextWidget(box=Box.xywh(80, 90, 0, 0), text='Ok', parent=d,
                        outline=1, sel_width=3, outline_radius=5,
                        action=submit, align=WidgetAlign.NONE, name='ok_btn')
        d.add_sel_widget(ok)
        self.pstack.push_panel(d)
        d.refresh()

    def _forget_wifi_network(self, row):
        profile = row['profile']
        result = self.handler.wifi_manager.delete_connection(profile['name'])
        if result is not None:
            d = MessageDialog(self.pstack, parse_nmcli_error(result), title="Error")
            self.pstack.push_panel(d)
            return
        self.pstack.pop_panel(None)  # pop submenu
        if self._wifi_networks_menu is not None:
            self.pstack.pop_panel(self._wifi_networks_menu)
        self.draw_wifi_menu(None, None)

    #
    # Title (Pedalboard and Preset)
    #
    def draw_title(self):
        self.draw_pedalboard(self.current.pedalboard.title)
        self.draw_preset(self.current.presets[self.current.preset_index])
        self.draw_info_message("")  # clear loading msg
        self.main_panel.refresh()

    def draw_pedalboard(self, pedalboard_name):
        pedalboard_name += ":"
        self.title_split = min(self.title_font.getmask(pedalboard_name).getbbox()[2], self.title_split_orig)
        if self.w_pedalboard is not None:
            self.w_pedalboard.set_text(pedalboard_name)
            self.w_pedalboard.set_box(box=Box.xywh(0, 20, self.title_split, 36), realign=True, refresh=True)
            return
        self.w_pedalboard = TextWidget(box=Box.xywh(0, 20, self.title_split, 36), text=pedalboard_name,
                                       font=self.title_font, parent=self.main_panel, action=self.draw_pedalboard_menu)
        self.main_panel.add_sel_widget(self.w_pedalboard)

    def draw_preset(self, preset_name):
        x = self.title_split + 4  # title_split gets set by draw_pedalboard
        width = self.display_width - x
        if self.w_preset is not None:
            self.w_preset.set_text(preset_name)
            self.w_preset.set_box(box=Box.xywh(x, 20, width, 36), realign=True, refresh=True)
            return
        self.w_preset = TextWidget(box=Box.xywh(x, 20, width, 36), text=preset_name, font=self.title_font,
                                   parent=self.main_panel, action=self.draw_preset_menu)
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

    def draw_selection_menu(self, items, title="", auto_dismiss=False, dismiss_option=False):
        # items is list of touples: (item_label, callback_method, callback_arg)
        # The below assumes that the callback takes the menu item label as an argument
        def menu_action(event, params):
            callback = params[1]
            if callback is not None:
                callback(params[2])

        m = Menu(title=title, items=items, auto_destroy=True, default_item=None, max_width=180, max_height=200,
                 auto_dismiss=auto_dismiss, dismiss_option=dismiss_option, action=menu_action)
        self.pstack.push_panel(m)
        return m

    def draw_message_dialog(self, text, title="Error"):
        d = MessageDialog(self.pstack, text, title=title)
        self.pstack.push_panel(d)

    #
    # Plugins
    #
    def draw_plugins(self):
        x = 0
        y = 78
        per_row = 4
        i = 1
        # erase currently rendered plugins and footswitches first
        for w in self.w_footswitches:
            w.destroy()
        self.w_footswitches = []
        for w in self.w_plugins:
            w.destroy()
        self.w_plugins = []

        for plugin in self.current.pedalboard.plugins:
            label = plugin.instance_id.replace('/', "")[:self.plugin_label_length]
            label = label.replace("_", "")
            label = self.shorten_name(label, self.plugin_width)
            p = TextWidget(box=Box.xywh(x, y, self.plugin_width, self.plugin_height), text=label, outline_radius=5,
                           parent=self.main_panel, action=self.plugin_event, object=plugin)
            p.set_font(self.small_font)
            self.color_plugin(p, plugin)
            self.main_panel.add_sel_widget(p)
            self.w_plugins.append(p)

            pos = (i % per_row)
            x = (self.plugin_width + 2) * pos
            if pos == 0:
                y = y + self.plugin_height + 2
            i += 1

            if plugin.has_footswitch:
                self.draw_footswitch(plugin)

        self.main_panel.refresh()
        self.footswitch_panel.refresh()

    def plugin_event(self, event, widget, plugin):
        if event == InputEvent.CLICK:
            self.handler.toggle_plugin_bypass(widget, plugin)
        elif event == InputEvent.LONG_CLICK:
            self.draw_parameter_menu(plugin)


    def color_plugin(self, widget, plugin):
        color = self.get_plugin_color(plugin)
        if plugin.is_bypassed() == True:
            widget.set_outline(1, color)
            widget.set_background(self.background)
            widget.set_foreground(self.foreground)
        else:
            widget.set_outline(2, self.background)
            widget.set_background(color)
            widget.set_foreground(self.background)

    def refresh_plugins(self):
        for w in self.w_plugins:
            plugin = w.object
            self.color_plugin(w, plugin)
        self.main_panel.refresh()

    def toggle_plugin(self, widget, plugin):
        self.color_plugin(widget, plugin)
        self.main_panel.refresh()

    # Try to map color to a valid displayable color, if not use foreground
    def valid_color(self, color):
        if color is None:
            return self.foreground
        try:
            return ImageColor.getrgb(color)
        except ValueError:
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
            taper = 2 if parameter.type == Parameter.Type.LOGARITHMIC else 1
            d = Parameterdialog(self.pstack, parameter.name, current_value, parameter.minimum, parameter.maximum,
                                width=270, height=130, auto_destroy=True, title=title, timeout=timeout,
                                action=self.parameter_commit, object=parameter, taper=taper)
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
    def draw_footswitch(self, plugin):
        for c in plugin.controllers:
            if isinstance(c, Footswitch):
                fs_id = c.id
                #fss[fs_id] = None
                if c.parameter.symbol != ":bypass":  # TODO token
                    label = c.parameter.name
                else:
                    label = self.shorten_name(plugin.instance_id, self.footswitch_width)
                c.set_display_label(label)

                y = 0
                x = self.get_footswitch_pitch() * fs_id
                self.footswitch_slots[fs_id] = label
                color = self.get_plugin_color(plugin)
                p = FootswitchWidget(Box.xywh(x, y, self.plugin_width, self.plugin_height), self.small_font,
                             label, color, plugin.is_bypassed(), parent=self.footswitch_panel, object=c)
                self.w_footswitches.append(p)
                self.footswitch_panel.add_widget(p)
                break

    def draw_unbound_footswitches(self):
        for fs in self.footswitches:
            if fs.id in self.footswitch_slots:
                continue
            slot = fs.id
            dl = fs.get_display_label()
            label = "" if dl is None else dl
            y = 0
            x = self.get_footswitch_pitch() * slot
            p = FootswitchWidget(Box.xywh(x, y, self.plugin_width, self.plugin_height), self.small_font,
                                 label, None, True, parent=self.footswitch_panel, object=fs)
            self.w_footswitches.append(p)
            self.footswitch_panel.add_widget(p)
        self.footswitch_panel.refresh()

    def update_footswitch(self, footswitch):
        for wfs in self.w_footswitches:
            if wfs.object == footswitch:
                wfs.toggle(footswitch.enabled == False)
                label = footswitch.get_display_label()
                if label:
                    wfs.label = label
                break
        self.footswitch_panel.refresh()
        self.refresh_plugins()  # TODO maybe not the most efficient, does exhibit some lag time

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
                 ("System shutdown", self.handler.system_menu_shutdown, None),
                 ("System reboot",  self.handler.system_menu_reboot, None),
                 ("Restart sound engine", self.handler.system_menu_restart_sound, None),
                 ("Bank Select >", self.draw_bank_menu, None),
                 ("Pedalboard Management >", self.draw_pedalboard_mgmt_menu, None)]
        self.draw_selection_menu(items, "System Menu")

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

    def draw_bank_menu(self, event):
        current_bank = self.handler.get_bank()
        items = [("None (All pedalboards)", self.handler.set_bank, None, current_bank==None)]
        for k,v in self.handler.get_banks().items():
            items.append((k, self.handler.set_bank, k, k==current_bank))
        self.draw_selection_menu(items, "Bank Select", auto_dismiss=True)

    def draw_wifi_menu(self, event, widget):
        connections = self.handler.wifi_manager.list_connections()
        active = util.DICT_GET(self.handler.wifi_status, 'connection')
        hotspot_active = util.DICT_GET(self.handler.wifi_status, 'hotspot_active')
        label = "Switch to Wifi" if hotspot_active else "Switch to Hotspot"
        items = []
        for conn in connections:
            is_active = conn['name'] == active
            items.append((conn['name'], self._draw_wifi_network_menu, conn, is_active))
        items.append(("Add Network...", self._draw_wifi_dialog, None))
        items.append((label, self.toggle_hotspot, None))
        self._wifi_networks_menu = self.draw_selection_menu(items, "WiFi Networks", dismiss_option=True)

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

    def draw_audio_parameter_dialog(self, name, symbol, value, min, max, commit_callback):
        d = util.DICT_GET(self.w_parameter_dialogs, symbol)
        if d is not None and d.parent is not None:
            return d

        d = Parameterdialog(self.pstack, name, value, min, max,
                            width=270, height=130, auto_destroy=True, title=name, timeout=2.2,
                            action=commit_callback, object=symbol, taper=1)
        self.w_parameter_dialogs[symbol] = d
        self.pstack.push_panel(d)
        return d

    def draw_vu_calibration_dialog(self, symbol, value, commit_callback):
        if value is None:
            value = 512  # 1024 / 2
        name = "VU Calibration"
        d = Parameterdialog(self.pstack, name, value, 502, 522,
                            width=270, height=130, auto_destroy=False, title=name, timeout=2.2,
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
        self.pstack.pop_panel(None)  # current panel
        self.pstack.pop_panel(self.footswitch_panel)
        if self.main_panel_pushed:
            self.pstack.pop_panel(self.main_panel)
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
        if util.DICT_GET(wifi_status, 'hotspot_active'):
            img = "wifi_orange.png"
        elif util.DICT_GET(wifi_status, 'wifi_connected'):
            img = "wifi_silver.png"
        else:
            img = "wifi_gray.png"
        image_path = os.path.join(self.imagedir, img)
        self.w_wifi.replace_img(image_path)

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

            if k is None:
                # Non-mapped control
                name = "none"
                control_type = Token.EXPRESSION if i == 0 else Token.KNOB  # HACK cuz we don't know type of unmapped
                color = Category.get_category_color(None)
                text_color =color
            else:
                # Mapped control or Volume
                control_type = util.DICT_GET(v, Token.TYPE)
                if control_type == Token.VOLUME:
                    name = "volume"
                    control_type = Token.KNOB
                    color = self.default_plugin_color
                    text_color = color
                else:
                    n = k.split(":")[1]
                    name = self.shorten_name(n, text_per_control)
                    color = util.DICT_GET(v, Token.COLOR)
                    if color is None:
                        # color not specified for control in config file
                        category = util.DICT_GET(v, Token.CATEGORY)
                        text_color = Category.get_category_color(category)
                        color = self.default_plugin_color

            if control_type == Token.KNOB:
                w = Icon(box=Box.xywh(x, y, 0, 0), text=name, text_color=text_color, parent=self.main_panel, outline=0)
                w.set_foreground(color)
                w.add_knob()
                self.w_controls.append(w)
            elif control_type == Token.EXPRESSION:
                w = Icon(box=Box.xywh(x, y, 0, 0), text=name, text_color=text_color, parent=self.main_panel, outline=0)
                w.set_foreground(color)
                w.add_pedal()
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
            test_size = self.small_font.getsize(test)[0]
            if test_size >= width:
                break
            text = test
        return text
