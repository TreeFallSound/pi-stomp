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

import pistomp.lcdbase as lcdbase


class Lcdcolor(lcdbase.Lcdbase):

    def __init__(self, cwd):
        super(Lcdcolor, self).__init__(cwd)

    def splash_show(self):
        return
        self.clear()
        self.draw.text((0, self.top + 30), "pi Stomp!", font=self.splash_font, fill=(255, 255, 255))
        self.refresh()

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

    def draw_title(self, pedalboard, preset, invert_pb, invert_pre):
        zone = 0
        self.erase_zone(zone)  # TODO to avoid redraw of entire zone, could we just redraw what changed?
        self.base_draw_title(self.draw[zone], self.title_font, pedalboard, preset, invert_pb, invert_pre)
        self.refresh_zone(zone)

    # Zone 1 - Analog Assignments (Tweak, Expression Pedal, etc.)
    def draw_analog_assignments(self, controllers):
        zone = 1
        self.erase_zone(zone)

        # Expression Pedal assignment
        type = 'EXPRESSION'  # TODO should this be an enum
        text = "None"
        self.draw[zone].line(((0, 5), (8, 1)), self.foreground, 1)
        self.draw[zone].line(((0, 5), (8, 5)), self.foreground, 2)
        if type in controllers:  # TODO Slightly lame string linkage to controller class
            text = "%s:%s" % (self.shorten_name(controllers[type][0], self.plugin_width),
                              self.shorten_name(controllers[type][1], self.plugin_width_medium))
        self.draw[zone].text((10, 2), text, self.foreground, self.small_font)

        # Tweak knob assignment
        type = 'KNOB'
        text = "None"
        x = 150  # TODO unique per display (half of width?)
        self.draw[zone].ellipse(((x, 0), (x + 6, 6)), self.foreground, 1)
        self.draw[zone].line(((x + 3, 0), (x + 3, 2)), self.background, 1)
        if type in controllers:
            text = "%s:%s" % (self.shorten_name(controllers[type][0], self.plugin_width),
                              self.shorten_name(controllers[type][1], self.plugin_width_medium))
        self.draw[zone].text((x+9, 2), text, self.foreground, self.small_font)

        self.refresh_zone(zone)

    def draw_info_message(self, text):
        zone = 1
        self.erase_zone(zone)
        self.draw[zone].text((0, 2), text, self.foreground, self.small_font)
        self.refresh_zone(zone)

    # Plugins
    def draw_plugin_select(self, plugin=None):
        width = 1
        if plugin is not None:
            # First unselct currently selected
            if self.selected_plugin:
                c = self.background if self.selected_plugin.has_footswitch else self.color_plugin
                self.draw_box_outline(self.selected_plugin.lcd_xyz[0], self.selected_plugin.lcd_xyz[1],
                                      self.selected_plugin.lcd_xyz[2], color=c, width=width)
                self.refresh_zone(self.selected_plugin.lcd_xyz[2])

            # Highlight new selection
            self.draw_box_outline(plugin.lcd_xyz[0], plugin.lcd_xyz[1], plugin.lcd_xyz[2], color=self.highlight,
                                  width=width)
            self.refresh_zone(plugin.lcd_xyz[2])
            self.selected_plugin = plugin

    def draw_bound_plugins(self, plugins, footswitches):
        zone = 7
        self.base_draw_bound_plugins(zone, plugins, footswitches)
        self.refresh_zone(zone)

    def draw_footswitch(self, xy1, xy2, zone, text, color):
        self.draw[zone].ellipse((xy1, xy2), fill=None, outline=color, width=self.footswitch_ring_width)
        self.draw[zone].text((xy1[0], xy2[1]), text, self.foreground, self.small_font)

    def draw_plugins(self, plugins):
        y = self.top
        x = self.left
        xwrap = self.width - self.plugin_width  # scroll if exceeds this width
        ymax = 64  # Maximum y for plugin LCD zone
        zone = 3
        self.erase_zone(3)
        self.erase_zone(5)

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
                zone += 2
                x = self.left
                if y >= ymax:
                    break  # Only display 2 rows, huge pedalboards won't fully render  # TODO make sure this works
        self.refresh_plugins()

    def draw_plugin(self, zone, x, y, text, width, eol, plugin, is_footswitch=False, color=0):
        text = self.shorten_name(text, width)
        y2 = y + self.plugin_height
        x2 = x + width
        if eol:
            x2 = x2 - 1
        xy1 = (x, y)
        xy2 = (x2, y2)

        if is_footswitch:
            if plugin:
                plugin.lcd_xyz = (xy1, xy2, zone)
            c = self.color_plugin_bypassed if plugin is None or plugin.is_bypassed() else color
            self.draw_footswitch(xy1, xy2, zone, text, c)
        elif plugin:
            plugin.lcd_xyz = (xy1, xy2, zone)
            self.draw_box(xy1, xy2, zone, text, is_footswitch, not plugin.is_bypassed(),
                          self.color_plugin)

        #bypass_indicator_xy = ((x+3, y+9), (x2-3, y+9))
        #plugin.bypass_indicator_xy = bypass_indicator_xy
        #self.draw[zone].line(bypass_indicator_xy, not plugin.is_bypassed(), self.plugin_bypass_thickness)

        return x2
