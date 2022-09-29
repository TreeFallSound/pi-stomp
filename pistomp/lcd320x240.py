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
import time
import functools
import logging
import os
import common.token as Token
import common.util as util
import pistomp.lcd as abstract_lcd
from PIL import ImageColor

import uilib
from uilib import *
from uilib.lcd_ili9341 import *
from pistomp import encoder
from pistomp import encoderswitch

from pistomp.footswitch import Footswitch  # TODO would like to avoid this module knowing such details


class Lcd(abstract_lcd.Lcd):

    def __init__(self, cwd, handler=None):
        self.cwd = cwd
        self.imagedir = os.path.join(cwd, "images")
        Config(os.path.join(cwd, 'ui', 'config.json'))
        self.handler = handler

        # TODO would be good to decouple the actual LCD hardware.  This file should work for any 320x240 display
        display = LcdIli9341(board.SPI(),
                             digitalio.DigitalInOut(board.CE0),
                             digitalio.DigitalInOut(board.D6),
                             digitalio.DigitalInOut(board.D5),
                             24000000)

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
        self.display_width = 320
        self.display_height = 240
        self.plugin_width = 78
        self.plugin_height = 31
        self.plugin_label_length = 7
        self.footswitch_height = 60

        # widgets
        self.w_wifi = None
        self.w_power = None
        self.w_wrench = None
        self.w_pedalboard = None
        self.w_preset = None
        self.w_plugins = []
        self.w_splash = None

        # panels
        self.pstack = PanelStack(display, image_format='RGB')
        self.splash_panel = Panel(box=Box.xywh(0, 0, self.display_width, self.display_height))
        self.pstack.push_panel(self.splash_panel)
        self.main_panel = Panel(box=Box.xywh(0, 0, self.display_width, 180))
        self.main_panel_pushed = False

        self.pedalboards = {}

        self.splash_show(True)

    #
    # Navigation
    #
    def enc_step(self, d):
        if d > 0:
            self.pstack.input_event(InputEvent.RIGHT)
        elif d < 0:
            self.pstack.input_event(InputEvent.LEFT)

    def enc_sw(self, v):
        if v == encoderswitch.Value.RELEASED:
            self.pstack.input_event(InputEvent.CLICK)
        elif v == encoderswitch.Value.LONGPRESSED:
            self.pstack.input_event(InputEvent.LONG_CLICK)

    #
    # Main
    #
    def link_data(self, pedalboards, current):
        self.pedalboards = pedalboards
        self.current = current

    def draw_main_panel(self):
        self.draw_tools(None, None, None)
        self.draw_title()
        self.draw_plugins()
        if not self.main_panel_pushed:
            self.pstack.push_panel(self.main_panel)
            self.main_panel_pushed = True
        #self.main_panel.refresh()

    #
    # Toolbar
    #
    def draw_tools(self, wifi_type=None, bypass_type=None, system_type=None):
        if self.w_wifi is not None:
            return
        self.w_wifi = ImageWidget(box=Box.xywh(240, 0, 20, 20), image_path=os.path.join(self.imagedir,
                                  'wifi_orange.png'), parent=self.main_panel, action=self.draw_wifi_dialog)
        self.main_panel.add_sel_widget(self.w_wifi)
        self.w_power = ImageWidget(box=Box.xywh(270, 0, 20, 20), image_path=os.path.join(self.imagedir,
                                   'power_green.png'), parent=self.main_panel)
        self.main_panel.add_sel_widget(self.w_power)
        self.w_wrench = ImageWidget(box=Box.xywh(296, 0, 20, 20), image_path=os.path.join(self.imagedir,
                             'wrench_silver.png'), parent=self.main_panel, action=self.draw_system_menu)
        self.main_panel.add_sel_widget(self.w_wrench)

    def draw_wifi_dialog(self, event, image):
        d = Dialog(width=240, height=120, auto_destroy=True, title='Configure WiFi')

        b = TextWidget(box=Box.xywh(0, 0, 0, 0), text='mySSID', prompt='SSID :', parent=d, outline=1, sel_width=3,
                       outline_radius=5,
                       action=lambda x, y: self.pstack.pop_panel(d), align=WidgetAlign.NONE, name='cancel_btn',
                       edit_message='WiFi SSID')
        d.add_sel_widget(b)
        b = TextWidget(box=Box.xywh(0, 30, 0, 0), text='password123', prompt='Password :', parent=d, outline=1,
                       sel_width=3, outline_radius=5,
                       action=lambda x, y: self.pstack.pop_panel(d), align=WidgetAlign.NONE, name='cancel_btn',
                       edit_message='Password')
        d.add_sel_widget(b)

        b = TextWidget(box=Box.xywh(0, 90, 0, 0), text='Cancel', parent=d, outline=1, sel_width=3, outline_radius=5,
                       action=lambda x, y: self.pstack.pop_panel(d), align=WidgetAlign.NONE, name='cancel_btn')
        d.add_sel_widget(b)
        b = TextWidget(box=Box.xywh(80, 90, 0, 0), text='Ok', parent=d, outline=1, sel_width=3, outline_radius=5,
                       action=lambda x, y: self.pstack.pop_panel(d), align=WidgetAlign.NONE, name='ok_btn')
        d.add_sel_widget(b)

        self.pstack.push_panel(d)
        d.refresh()

    #
    # Title (Pedalboard and Preset)
    #
    def draw_title(self):
        self.draw_pedalboard(self.current.pedalboard.title)
        self.draw_preset(self.current.presets[self.current.preset_index])
        self.main_panel.refresh()

    def draw_pedalboard(self, pedalboard_name):
        if self.w_pedalboard is not None:
            self.w_pedalboard.set_text(pedalboard_name)
            return

        self.w_pedalboard = TextWidget(box=Box.xywh(0, 20, 159, 36), text=pedalboard_name, font=self.title_font,
                                       parent=self.main_panel, action=self.draw_pedalboard_menu)
        self.main_panel.add_sel_widget(self.w_pedalboard)

    def draw_preset(self, preset_name):
        if self.w_preset is not None:
            self.w_preset.set_text(preset_name)
            return

        self.w_preset = TextWidget(box=Box.xywh(161, 20, 159, 36), text=preset_name, font=self.title_font,
                                   parent=self.main_panel, action=self.draw_preset_menu)
        self.main_panel.add_sel_widget(self.w_preset)

    def draw_pedalboard_menu(self, event, widget):
        items = []
        for p in self.pedalboards:
            items.append((p.title, self.handler.pedalboard_change, p))
        self.draw_selection_menu(items, "Pedalboards")

    def draw_preset_menu(self, event, widget):
        items = []
        for (i, name) in self.current.presets.items():
            items.append((name, self.handler.preset_change, i))
        self.draw_selection_menu(items, "Snapshots")

    def draw_selection_menu(self, items, title=""):
        # items is list of touples: (item_label, callback_method, callback_arg)
        # The below assumes that the callback takes the menu item label as an argument
        def menu_action(event, params):
            callback = params[1]
            if callback is not None:
                callback(params[2])

        items.append(('\u2b05', None))  # Back arrow
        m = Menu(title=title, items=items, auto_destroy=True, default_item=None, max_width=180, max_height=180,
                 action=menu_action)
        self.pstack.push_panel(m)

    #
    # Plugins
    #
    def draw_plugins(self):
        x = 0
        y = 81
        per_row = 4
        i = 1
        # erase currently rendered plugins first
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
        self.main_panel.refresh()

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
        d = Parameterdialog(self.pstack, parameter.name, parameter.value, parameter.minimum, parameter.maximum,
                            width=270, height=130, auto_destroy=True, title=parameter.name,
                            action=self.parameter_commit, object=parameter)
        self.pstack.push_panel(d)

    def parameter_commit(self, parameter, value):
        self.handler.parameter_value_commit(parameter, value)

    #
    # System Menu
    #
    def draw_system_menu(self, event, widget):
        items = [("System shutdown", self.handler.system_menu_shutdown, None),
                 ("System reboot",  self.handler.system_menu_reboot, None),
                 ("Save current pedalboard", self.handler.system_menu_save_current_pb, None),
                 ("Reload pedalboards", self.handler.system_menu_reload, None),
                 ("Restart sound engine", self.handler.system_menu_restart_sound, None),
                 ("Input Gain", self.handler.system_menu_input_gain, None),
                 ("Headphone Volume", self.handler.system_menu_headphone_volume, None)]
        self.draw_selection_menu(items, "System menu")

    def draw_audio_parameter_dialog(self, name, symbol, value, min, max, commit_callback):
        d = Parameterdialog(self.pstack, name, value, min, max,
                            width=270, height=130, auto_destroy=True, title=name,
                            action=commit_callback, object=symbol)
        self.pstack.push_panel(d)

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
        pass

    def update_bypass(self, bypass):
        pass
    
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
        pass

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
