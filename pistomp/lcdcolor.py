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

import os
import pistomp.category as Category
import pistomp.lcdbase as lcdbase
import common.token as Token
import common.util as util

class Lcdcolor(lcdbase.Lcdbase):

    def __init__(self, cwd):
        super(Lcdcolor, self).__init__(cwd)

    # Menu Screens (uses deep_edit image and draw objects)
    def menu_show(self, page_title, menu_items):
        pass

    def menu_highlight(self, index):
        pass

    # Parameter Value Edit
    def draw_value_edit(self, plugin_name, parameter, value):
        self.draw_title(plugin_name, None, False, False, False)
        self.draw_value_edit_graph(parameter, value)

    def draw_value_edit_graph(self, parameter, value):
        # TODO super inefficient here redrawing the whole image every time the value changes
        self.draw_title(parameter.name, None, False, False, False)
        self.menu_image.paste(0, (0, 0, self.width, self.menu_image_height))

        y0 = self.menu_y0
        y1 = y0 - 2
        ytext = y0 // 2
        x = 0
        xpitch = 4

        # The current value text
        self.menu_draw.text((0, ytext), "%s" % util.format_float(value), self.foreground, self.title_font)

        val = util.renormalize(value, parameter.minimum, parameter.maximum, 0, self.graph_width)
        yref = y1
        while x < self.graph_width:
            self.menu_draw.line(((x + 2, y0), (x + 2, yref)), self.color_plugin, 1)
            if (x < val) and (x % xpitch) == 0:
                self.menu_draw.rectangle(((x, y0), (x + 2, y1)), self.highlight, 2)
                y1 = y1 - 1
            x = x + xpitch
            yref = yref - 1

        self.menu_draw.text((0, self.menu_y0 + 4), "%d" % parameter.minimum, self.foreground, self.small_font)
        self.menu_draw.text((self.graph_width - (len(str(parameter.maximum)) * 4), self.menu_y0 + 4),
                            "%d" % parameter.maximum, self.foreground, self.small_font)
        self.refresh_menu()
        self.draw_info_message("Click to exit")

    def update_wifi(self, wifi_status):
        if not self.supports_toolbar:
            return
        if util.DICT_GET(wifi_status, 'hotspot_active'):
            img = "wifi_orange.png"
        elif util.DICT_GET(wifi_status, 'wifi_connected'):
            img = "wifi_silver.png"
        else:
            img = "wifi_gray.png"
        path = os.path.join(self.imagedir, img)
        self.change_tool_img(self.tool_wifi, path)

    def update_eq(self, eq_status):
        if not self.supports_toolbar:
            return
        img = "eq_blue.png" if eq_status else "eq_gray.png"
        path = os.path.join(self.imagedir, img)
        self.change_tool_img(self.tool_eq, path)

    def update_bypass(self, bypass):
        if not self.supports_toolbar:
            return
        img = "power_green.png" if bypass else "power_gray.png"
        path = os.path.join(self.imagedir, img)
        self.change_tool_img(self.tool_bypass, path)

    def change_tool_img(self, tool, img_path):
        if not self.supports_toolbar:
            return
        tool.update_img(img_path)
        self.images[self.ZONE_TOOLS].paste(tool.image, (tool.x, tool.y))
        self.refresh_zone(self.ZONE_TOOLS)

    def clear_select(self):
        if self.selected_box:
            self.draw_box_outline(self.selected_box[0], self.selected_box[1], self.ZONE_TOOLS,
                                  color=self.background, width=self.selected_box[2])
            self.refresh_zone(self.ZONE_TOOLS)
            self.selected_box = None

    def draw_title(self, pedalboard, preset, invert_pb, invert_pre, highlight_only=False):
        zone = self.ZONE_TITLE
        self.erase_zone(zone)  # TODO to avoid redraw of entire zone, could we just redraw what changed?
        self.base_draw_title(self.draw[zone], self.title_font, pedalboard, preset, invert_pb, invert_pre,
                             highlight_only)
        self.refresh_zone(zone)

    # Zone 1 - Analog Assignments (Tweak, Expression Pedal, etc.)
    def draw_knob(self, text, x, color="gray"):
        zone = self.ZONE_ASSIGNMENTS
        self.draw[zone].ellipse(((x, 3), (x + 14, 17)), self.background, color, 2)
        self.draw[zone].line(((x + 12, 5), (x + 7, 10)), color, 2)
        self.draw[zone].text((x + 19, 1), text, self.foreground, self.tiny_font)

    def draw_pedal(self, text, x, color="gray"):
        zone = self.ZONE_ASSIGNMENTS
        self.draw[zone].line(((x, 14), (x + 13, 4)), color, 2)
        self.draw[zone].line(((x, 14), (x + 14, 14)), color, 4)
        self.draw[zone].text((x + 19, 1), text, self.foreground, self.tiny_font)

    def draw_analog_assignments(self, controllers):
        zone = self.ZONE_ASSIGNMENTS
        self.erase_zone(zone)

        # spacing and scaling of text
        width_per_control = self.width
        text_per_control = self.width
        num = len(controllers)
        if num > 0:
            width_per_control = int(round(self.width / num))
            text_per_control = width_per_control - 16  # minus width of control icon

        x = 0
        for k, v in controllers.items():
            control_type = util.DICT_GET(v, Token.TYPE)
            color = util.DICT_GET(v, Token.COLOR)
            if color is None:
                # color not specified for control in config file
                category = util.DICT_GET(v, Token.CATEGORY)
                color = Category.get_category_color(category)
            name = k.split(":")[1]
            n = self.shorten_name(name, text_per_control)
            if control_type == Token.KNOB:
                self.draw_knob(n, x, color)
            if control_type == Token.EXPRESSION:
                self.draw_pedal(n, x, color)
            x += width_per_control

        self.refresh_zone(zone)

    def draw_info_message(self, text):
        zone = self.ZONE_TOOLS
        self.erase_zone(zone)
        self.draw[zone].text((0, 0), text, self.foreground, self.tiny_font)
        self.refresh_zone(zone)

    # Plugins
    def draw_plugin_select(self, plugin=None):
        width = 2
        # First unselect currently selected
        if self.selected_plugin:
            x0 = self.selected_plugin.lcd_xyz[0][0] - 3
            y0 = self.selected_plugin.lcd_xyz[0][1] - 3
            x1 = self.selected_plugin.lcd_xyz[1][0] + 3
            y1 = self.selected_plugin.lcd_xyz[1][1] + 3
            c = self.background # if self.selected_plugin.has_footswitch else self.get_plugin_color(self.selected_plugin)
            self.draw_box_outline((x0, y0), (x1, y1), self.selected_plugin.lcd_xyz[2], color=c, width=width)
            self.refresh_zone(self.selected_plugin.lcd_xyz[2])

        if plugin is not None:
            # Highlight new selection
            x0 = plugin.lcd_xyz[0][0] - 3
            y0 = plugin.lcd_xyz[0][1] - 3
            x1 = plugin.lcd_xyz[1][0] + 3
            y1 = plugin.lcd_xyz[1][1] + 3
            self.draw_box_outline((x0, y0), (x1, y1), plugin.lcd_xyz[2], color=self.highlight, width=width)
            self.refresh_zone(plugin.lcd_xyz[2])
            self.selected_plugin = plugin

    def draw_bound_plugins(self, plugins, footswitches):
        zone = self.ZONE_FOOTSWITCHES
        self.erase_zone(zone)   # necessary when changing pedalboards with different switch assignments
        self.base_draw_bound_plugins(zone, plugins, footswitches)
        self.refresh_zone(zone)

    def draw_footswitch(self, xy1, xy2, zone, text, color):
        # implement in display class
        pass

    def draw_plugins(self, plugins):
        y = self.top + 3
        x = self.left
        xwrap = self.width - self.plugin_width  # scroll if exceeds this width
        ymax = 64  # Maximum y for plugin LCD zone
        zone = self.ZONE_PLUGINS1
        self.erase_zone(self.ZONE_PLUGINS1)
        self.erase_zone(self.ZONE_PLUGINS2)
        self.erase_zone(self.ZONE_PLUGINS3)

        count = 0
        for p in plugins:
            if not p.has_footswitch:
                count = count + 1
        width = self.plugin_width_medium if count <= 8 else self.plugin_width

        count = 0
        eol = False
        for p in plugins:
            if p.has_footswitch:
                continue
            label = p.instance_id.replace('/', "")[:self.plugin_label_length]
            label = label.replace("_", "")
            count += 1
            if count > 4:
                eol = True
                count = 0
            x = self.draw_plugin(zone, x, y, label, width, eol, p)
            eol = False
            x = x + self.plugin_rect_x_pad
            if x > xwrap:
                zone += 1
                x = self.left
                if y >= ymax:
                    break  # Only display 2 rows, huge pedalboards won't fully render  # TODO make sure this works
        self.refresh_plugins()

    def draw_plugin(self, zone, x, y, text, width, eol, plugin, is_footswitch=False, color=0):
        text = self.shorten_name(text, width)

        y2 = y + (self.footswitch_height if is_footswitch else self.plugin_height)
        x2 = x + width
        if eol:
            x2 = x2 - 1
        xy1 = (x, y)
        xy2 = (x2, y2)

        if is_footswitch:
            if plugin:
                plugin.lcd_xyz = (xy1, xy2, zone)
            c = self.color_plugin_bypassed if plugin is not None and plugin.is_bypassed() else color
            self.draw_footswitch(xy1, xy2, zone, text, c)
        elif plugin:
            plugin.lcd_xyz = (xy1, xy2, zone)
            self.draw_box(xy1, xy2, zone, text, is_footswitch, not plugin.is_bypassed(), self.get_plugin_color(plugin))

        return x2
