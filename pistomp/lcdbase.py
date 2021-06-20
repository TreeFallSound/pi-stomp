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
import pistomp.lcd as abstract_lcd

from pistomp.footswitch import Footswitch  # TODO would like to avoid this module knowing such details


class Lcdbase(abstract_lcd.Lcd):

    def __init__(self, cwd):

        # The following parameters need to be specified by the concrete subclass

        # Fonts
        self.title_font = None
        self.splash_font = None
        self.small_font = None

        # Colors
        self.background = None
        self.foreground = None
        self.highlight = None
        self.color_plugin = None
        self.color_plugin_bypassed = None

        # Dimensions
        self.width = None
        self.height = None
        self.top = None
        self.left = None
        self.zone_height = None
        self.zone_y = None
        self.flip = False
        self.footswitch_xy = None
        self.footswitch_width = None
        self.plugin_height = None
        self.plugin_width = None
        self.plugin_width_medium = None
        self.plugin_rect_x_pad = None
        self.plugin_bypass_thickness = None
        self.plugin_label_length = None
        self.footswitch_width = None
        self.footswitch_ring_width = None

        # Content
        self.zones = None
        self.zone_height = None
        self.footswitch_xy = None
        self.images = None
        self.draw = None
        self.selected_plugin = None


    # This method verifies that each variable declared above in __init__ gets assigned a value by the object class
    # It might flag vars which get assigned a value of None intentionally by the object class
    # A better solution might be to create these as abstract properties, but then they are accessed as strings
    # which is likely worse
    def check_vars_set(self):
        known_exceptions = ["selected_plugin"]
        for v in self.__dict__:
            if getattr(self, v) is None:
                if v not in known_exceptions:
                    logging.error("%s class doesn't set variable: %s" % (self, v))

    # Convert zone height values to absolute y values considering the flip setting
    def calc_zone_y(self):
        y_offset = 0 if not self.flip else self.height
        for i in range(self.zones):
            if self.flip:
                y_offset -= (self.zone_height[i])
                if y_offset < 0:
                    break
            else:
                if i != 0:
                    y_offset += (self.zone_height[i-1])
                    if y_offset > self.height:
                        break
            self.zone_y[i] = y_offset

    def splash_show(self):
        pass

    def base_draw_title(self, draw, font, pedalboard, preset, invert_pb, invert_pre):
        pb_size  = font.getsize(pedalboard)[0]
        font_height = font.getsize(pedalboard)[1]
        x0 = self.left
        y = self.top  # negative pushes text to top of LCD
        highlight_color = self.highlight

        # Pedalboard Name
        if invert_pb:
            draw.rectangle(((x0, y), (pb_size, font_height - 2)), True, highlight_color)
        draw.text((x0, y), pedalboard, self.foreground, font)

        if preset != None:

            # delimiter
            delimiter = "/"
            x = x0 + pb_size + 1
            draw.text((x, y), delimiter, self.foreground, font)

            # Preset Name
            pre_size = font.getsize(preset)[0]
            x = x + font.getsize(delimiter)[0]
            x2 = x + pre_size
            y2 = font_height
            if invert_pre:
                draw.rectangle(((x, y), (x2, y2 - 2)), True, highlight_color)
            draw.text((x, y), preset, self.foreground, font)

    def base_draw_bound_plugins(self, zone, plugins, footswitches):
        bypass_label = "byps"
        fss = footswitches.copy()
        for p in plugins:
            if p.has_footswitch is False:
                continue
            for c in p.controllers:
                if isinstance(c, Footswitch):
                    fs_id = c.id
                    fss[fs_id] = None
                    if c.parameter.symbol != ":bypass":  # TODO token
                        label = c.parameter.name
                    else:
                        label = self.shorten_name(p.instance_id, self.footswitch_width)
                    self.draw_plugin(zone, self.footswitch_xy[fs_id][0], self.footswitch_xy[fs_id][1], label,
                                     self.footswitch_width, False, p, True, self.footswitch_xy[fs_id][2])

        # Draw any footswitches which weren't found to be bound to a plugin
        for fs_id in range(len(fss)):
            if fss[fs_id] is None:
                continue
            label = "" if fss[fs_id].display_label is None else fss[fs_id].display_label
            #xy2 = (self.footswitch_xy[fs_id][0] + self.footswitch_width, self.footswitch_xy[fs_id][1] + self.plugin_height)
            self.draw_plugin(zone, self.footswitch_xy[fs_id][0], self.footswitch_xy[fs_id][1], label,
                             self.footswitch_width, False, None, True, self.footswitch_xy[fs_id][2])
            #self.draw_box((self.footswitch_xy[fs_id][0], self.footswitch_xy[fs_id][1]), xy2, zone, label, True)

    def draw_box(self, xy, xy2, zone, text=None, round_bottom_corners=False, fill=False, color=None, width=1):
        if color is None:
            color = self.foreground
        f = color if fill else self.background
        self.draw[zone].rectangle((xy, xy2), f, outline=color, width=width)
        #self.draw[zone].point(xy, self.background)  # Round the top corners
        #self.draw[zone].point((xy2[0],xy[1]), self.background)
        #if round_bottom_corners:
        #    self.draw[zone].point((xy[0],xy2[1]))
        #    self.draw[zone].point((xy2[0],xy2[1]))
        if text:
            f = self.background if fill else self.foreground
            self.draw[zone].text((xy[0] + 2, xy[1] + 2), text, f, self.small_font)

    def draw_box_outline(self, xy, xy2, zone, color, width=2):
        self.draw[zone].line((xy, (xy[0], xy2[1])), color, width)
        self.draw[zone].line((xy, (xy2[0], xy[1])), color, width)
        self.draw[zone].line((xy2, (xy[0], xy2[1])), color, width)
        self.draw[zone].line((xy2, (xy2[0], xy[1])), color, width)

    def erase_all(self):
        for z in range(self.zones):
            self.erase_zone(z)
        for z in range(self.zones):
            self.refresh_zone(z)

    def erase_zone(self, zone_idx):
        self.images[zone_idx].paste(self.background, (0, 0, self.width, self.zone_height[zone_idx]))

    def shorten_name(self, name, width):
        text = ""
        for x in name.lower().replace('_', '').replace('/', '').replace(' ', ''):
            test = text + x
            test_size = self.small_font.getsize(test)[0]
            if test_size >= width:
                break
            text = test
        return text
