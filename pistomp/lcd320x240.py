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
import common.token as Token
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
        self.plugin_height = 31
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
        self.w_eq = None
        self.w_power = None
        self.w_wrench = None
        self.w_pedalboard = None
        self.w_preset = None
        self.w_plugins = []
        self.w_footswitches = []
        self.w_splash = None
        self.w_info_msg = None

        # panels
        self.pstack = PanelStack(display, image_format='RGB', use_dimming=False)  # TODO use dimming without loosing FS's
        self.splash_panel = Panel(box=Box.xywh(0, 0, self.display_width, self.display_height))
        self.pstack.push_panel(self.splash_panel)
        self.main_panel = Panel(box=Box.xywh(0, 0, self.display_width, 170))
        self.main_panel_pushed = False
        self.footswitch_panel = Panel(box=Box.xywh(0, 180, self.display_width, 60))
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
    def link_data(self, pedalboards, current):
        self.pedalboards = pedalboards
        self.current = current

    def draw_main_panel(self):
        self.draw_tools(None, None, None, None)
        self.draw_title()
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
                                  'wifi_orange.png'), parent=self.main_panel, action=self.draw_wifi_dialog)
        self.main_panel.add_sel_widget(self.w_wifi)
        if self.w_eq is not None:
            return
        self.w_eq = ImageWidget(box=Box.xywh(240, 0, 20, 20), image_path=os.path.join(self.imagedir,
                                  'eq_blue.png'), parent=self.main_panel, action=self.draw_audio_menu)
        self.main_panel.add_sel_widget(self.w_eq)
        self.w_power = ImageWidget(box=Box.xywh(270, 0, 20, 20), image_path=os.path.join(self.imagedir,
                                   'power_gray.png'), parent=self.main_panel, action=self.handler.system_toggle_bypass)
        self.main_panel.add_sel_widget(self.w_power)
        self.w_wrench = ImageWidget(box=Box.xywh(296, 0, 20, 20), image_path=os.path.join(self.imagedir,
                             'wrench_silver.png'), parent=self.main_panel, action=self.draw_system_menu)
        self.main_panel.add_sel_widget(self.w_wrench)

    def draw_wifi_dialog(self, event, image):
        # The below seems to crash due to 'Lcd' object has no attribute 'current_ssid' 'current_password'
        # self.handler.get_wifi_credentials(current_ssid, current_password)
        
        d = Dialog(width=240, height=120, auto_destroy=True, title='Configure WiFi')

        self.w_wifi_ssid = TextWidget(box=Box.xywh(0, 0, 0, 0), text='mySSID', prompt='SSID :', parent=d, outline=1, sel_wi>
                   outline_radius=5, align=WidgetAlign.NONE, name='cancel_btn', edit_message='WiFi SSID')
        d.add_sel_widget(self.w_wifi_ssid)
        self.ssid = self.w_wifi_ssid.edit_message
        
        self.w_wifi_pass = TextWidget(box=Box.xywh(0, 30, 0, 0), text='password123', prompt='Password :', parent=d, outline=1,
                   sel_width=3, outline_radius=5, align=WidgetAlign.NONE, name='cancel_btn', edit_message='Password')
        d.add_sel_widget(self.w_wifi_pass)
        self.password = self.w_wifi_pass.edit_message

        b = TextWidget(box=Box.xywh(0, 60, 0, 0), text='Hotspot', parent=d, outline=1, sel_width=3, outline_radius=5,
                   action=self.handler.system_toggle_hotspot, align=WidgetAlign.NONE)
        d.add_sel_widget(b)

        b = TextWidget(box=Box.xywh(0, 90, 0, 0), text='Cancel', parent=d, outline=1, sel_width=3, outline_radius=5,
                   action=lambda x, y: self.pstack.pop_panel(d), align=WidgetAlign.NONE, name='cancel_btn')
        d.add_sel_widget(b)

        b = TextWidget(box=Box.xywh(80, 90, 0, 0), text='Ok', parent=d, outline=1, sel_width=3, outline_radius=5,
                   action=self._commit_wifi_settings, align=WidgetAlign.NONE, name='ok_btn')
        d.add_sel_widget(b)

        self.pstack.push_panel(d)
        self.w_wifi_dialog = d
        d.refresh()
        
    def _commit_wifi_settings(self, a, b):
        ssid = self.w_wifi_ssid.get_text()
        # password = self.w_wifi_password.get_text()
        # print("commit_wifi_settings", ssid)
        # self.handler.configure_wifi_credentials(ssid, password)
        self.pstack.pop_panel(self.w_wifi_dialog)

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
        for p in self.pedalboards:
            items.append((p.title, self.handler.pedalboard_change, p))
        self.draw_selection_menu(items, "Pedalboards", auto_dismiss=True)

    def draw_preset_menu(self, event, widget):
        items = []
        for (i, name) in self.current.presets.items():
            items.append((name, self.handler.preset_change, i))
        self.draw_selection_menu(items, "Snapshots", auto_dismiss=True)

    def draw_selection_menu(self, items, title="", auto_dismiss=False):
        # items is list of touples: (item_label, callback_method, callback_arg)
        # The below assumes that the callback takes the menu item label as an argument
        def menu_action(event, params):
            callback = params[1]
            if callback is not None:
                callback(params[2])

        m = Menu(title=title, items=items, auto_destroy=True, default_item=None, max_width=180, max_height=180,
                 auto_dismiss=auto_dismiss, action=menu_action)
        self.pstack.push_panel(m)

    #
    # Plugins
    #
    def draw_plugins(self):
        x = 0
        y = 72
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
        for (name, param) in plugin.parameters.items():
            if name != Token.COLON_BYPASS:
                items.append((name, self.draw_parameter_dialog, param))
        self.draw_selection_menu(items, "Parameters")

    def draw_parameter_dialog(self, parameter):
        title = parameter.instance_id + ":" + parameter.name
        d = Parameterdialog(self.pstack, parameter.name, parameter.value, parameter.minimum, parameter.maximum,
                            width=270, height=130, auto_destroy=True, title=title, timeout=2.2,
                            action=self.parameter_commit, object=parameter)
        self.pstack.push_panel(d)
        return d

    def parameter_commit(self, parameter, value):
        self.handler.parameter_value_commit(parameter, value)

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
        for slot in [ele for ele in range(self.handler.get_num_footswitches()) if ele not in self.footswitch_slots]:
            y = 0
            x = self.get_footswitch_pitch() * slot
            p = FootswitchWidget(Box.xywh(x, y, self.plugin_width, self.plugin_height), self.small_font,
                                 "", None, True, parent=self.footswitch_panel)
            self.w_footswitches.append(p)
            self.footswitch_panel.add_widget(p)
        self.footswitch_panel.refresh()

    def update_footswitch(self, footswitch):
        for wfs in self.w_footswitches:
            if wfs.object == footswitch:
                wfs.toggle(footswitch.enabled == False)
                break
        self.footswitch_panel.refresh()
        self.refresh_plugins()  # TODO maybe not the most efficient, does exhibit some lag time

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
        items = [("System shutdown", self.handler.system_menu_shutdown, None),
                 ("System reboot",  self.handler.system_menu_reboot, None),
                 ("Save current pedalboard", self.handler.system_menu_save_current_pb, None),
                 ("Reload pedalboards", self.handler.system_menu_reload, None),
                 ("Restart sound engine", self.handler.system_menu_restart_sound, None)]
        self.draw_selection_menu(items, "System Menu")

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
        d = Parameterdialog(self.pstack, name, value, min, max,
                            width=270, height=130, auto_destroy=False, title=name, timeout=2.2,
                            action=commit_callback, object=symbol)
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
        self.w_splash.set_foreground(self.color_splash_down)
        self.splash_panel.refresh()
        self.pstack.pop_panel(self.main_panel)
    
    def clear(self):
        pass

    def erase_all(self):
        pass

    def clear_select(self):
        pass

    # Toolbar
    def update_wifi(self, wifi_status):
        img = 'wifi_silver.png' if wifi_status else 'wifi_orange.png'
        image_path = os.path.join(self.imagedir, img)
        self.w_wifi.replace_img(image_path)

    def update_eq(self, eq_status):
        img = 'eq_blue.png' if eq_status else 'eq_gray.png'
        image_path = os.path.join(self.imagedir, img)
        self.w_eq.replace_img(image_path)

    def update_bypass(self, bypass):
        img = 'power_gray.png' if bypass else 'power_green.png'
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
        pass
    
    def draw_info_message(self, text):
        if self.w_info_msg is None:
            self.w_info_msg = TextWidget(box=Box.xywh(0, 0, 0, 0), text='', parent=self.main_panel, outline=0,
                                         sel_width=0)
        else:
            self.w_info_msg.set_text(text)

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
