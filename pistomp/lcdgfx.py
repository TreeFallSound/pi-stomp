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

import signal
import spidev
import common.token as Token
import common.util as util
import pistomp.lcd as abstract_lcd
import common.util as util

from gfxhat import touch, lcd, backlight, fonts
from PIL import Image, ImageFont, ImageDraw

from pistomp.footswitch import Footswitch  # TODO would like to avoid this module knowing such details


class Lcd(abstract_lcd.Lcd):
    __single = None

    def __init__(self):
        if Lcd.__single:
            raise Lcd.__single
        Lcd.__single = self

        # GFX properties
        self.width, self.height = lcd.dimensions()
        self.height -= 1  # TODO figure out why this is needed
        self.num_leds = 6

        # Zone dimensions
        self.zone_height = {0: 12,
                            1: 8,
                            2: 2,
                            3: 13,
                            4: 2,
                            5: 13,
                            6: 2,
                            7: 12}

        self.footswitch_xy = {0: (0,   0),
                              1: (51,  0),
                              2: (101, 0)}

        # Menu (System menu, Parameter edit, etc.)
        self.menu_height = self.height - self.zone_height[0] + 1  # TODO figure out why +1
        self.menu_image_height = self.menu_height * 10  # 10 pages (~40 parameters) enough?
        self.menu_image = Image.new('L', (self.width, self.menu_image_height))
        self.menu_draw = ImageDraw.Draw(self.menu_image)
        self.menu_y0 = 40

        # Element dimensions
        self.plugin_height = 11
        self.plugin_width = 24
        self.plugin_width_medium = 30
        self.plugin_bypass_thickness = 2
        self.plugin_label_length = 7
        self.footswitch_width = 26

        self.images = [Image.new('L', (self.width, self.zone_height[0])),  # Pedalboard / Preset Title bar
                       Image.new('L', (self.width, self.zone_height[1])),  # Analog Controllers
                       Image.new('L', (self.width, self.zone_height[2])),  # Plugin selection
                       Image.new('L', (self.width, self.zone_height[3])),  # Plugins Row 1
                       Image.new('L', (self.width, self.zone_height[4])),  # Plugin selection
                       Image.new('L', (self.width, self.zone_height[5])),  # Plugins Row 2
                       Image.new('L', (self.width, self.zone_height[6])),  # Plugin selection
                       Image.new('L', (self.width, self.zone_height[7]))]  # Footswitch Plugins

        self.draw = [ImageDraw.Draw(self.images[0]), ImageDraw.Draw(self.images[1]),
                     ImageDraw.Draw(self.images[2]), ImageDraw.Draw(self.images[3]),
                     ImageDraw.Draw(self.images[4]), ImageDraw.Draw(self.images[5]),
                     ImageDraw.Draw(self.images[6]), ImageDraw.Draw(self.images[7])]

        # Load fonts
        self.splash_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 18)
        self.title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 11)
        self.label_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 10)
        self.small_bold_font = ImageFont.truetype("DejaVuSansMono-Bold.ttf", 8)
        #self.small_font = ImageFont.truetype("DejaVuSansMono.ttf", 8)
        self.small_font = ImageFont.truetype("/home/patch/pi-stomp/fonts/EtBt6001-JO47.ttf", 6)

        # Splash
        text_im = Image.new('L', (103, 63))
        draw = ImageDraw.Draw(text_im)
        draw.text((7, 20), "pi Stomp!", True, self.splash_font)
        self.splash = Image.new('L', (self.width, self.height))
        self.splash.paste(text_im.rotate(24), (0, 0, 103, 63))
        self.splash_show()

        # Turn on Backlight
        self.enable_backlight()

    def splash_show(self):
        for x in range(0, self.width):
            for y in range(0, self.height):
                pixel = self.splash.getpixel((x, y))
                lcd.set_pixel(self.width - x - 1, self.height - y, pixel)
        lcd.show()

    def refresh_zone(self, zone_idx):
        #flipped = self.images[zone_idx].transpose(Image.ROTATE_180)
        flipped = self.images[zone_idx]

        # Determine the start y position by adding the height of all previous zones
        y_offset = 0
        for i in range(zone_idx):
            y_offset += self.zone_height[i]

        # Set Pixels
        # TODO make common method
        for x in range(0, self.width):
            for y in range(0, self.zone_height[zone_idx]):
                pixel = flipped.getpixel((x, y))
                lcd.set_pixel(self.width - x - 1, self.height - y - y_offset, pixel)
        lcd.show()

    def refresh_menu(self, highlight_range=None, scroll_offset=0):
        # Set Pixels
        y_offset = self.zone_height[0]
        for x in range(0, self.width):
            for y in range(0, self.menu_height):
                y_draw = y + scroll_offset
                if y_draw < self.menu_image_height:
                    pixel = self.menu_image.getpixel((x, y_draw))
                    if highlight_range and (y_draw >= highlight_range[0]) and (y_draw <= highlight_range[1]):  # TODO LAME
                         pixel = not pixel
                    lcd.set_pixel(self.width - x - 1, self.height - y - y_offset, pixel)
        lcd.show()

    def refresh_plugins(self):
        self.refresh_zone(7)
        self.refresh_zone(5)
        self.refresh_zone(3)

    def enable_backlight(self):
        for x in range(6):
            backlight.set_pixel(x, 50, 100, 100)
        backlight.show()

    def cleanup(self):
        backlight.set_all(0, 0, 0)
        backlight.show()
        lcd.clear()
        lcd.show()
        for i in range(0, self.num_leds):
            touch.set_led(i, 0)

    def clear(self):
        for x in range(6):
            backlight.set_pixel(x, 0, 0, 0)
            touch.set_led(x, 0)
        backlight.show()
        lcd.clear()
        lcd.show()

    # Menu Screens (uses deep_edit image and draw objects)
    def menu_show(self, page_title, menu_items):
        # Title (plugin name)
        self.images[0].paste(0, (0, 0, self.width, self.zone_height[0]))
        self.draw[0].text((0, -2), page_title, True, self.title_font)
        self.refresh_zone(0)

        self.menu_image.paste(0, (0, 0, self.width, self.menu_height))

        # Menu Items
        idx = 0
        x = 0
        y = 2
        menu_list = list(sorted(menu_items))
        for i in menu_list:
            if idx is 0:
                self.menu_draw.text((x, y), "%s" % menu_items[i][Token.NAME], True, self.small_font)
                x = 8   # indent after first element (back button)
            else:
                self.menu_draw.text((x, y), "%d %s" % (idx, menu_items[i][Token.NAME]), True, self.small_font)
            y += 10
            idx += 1
        self.refresh_menu()  # TODO Change name

    def menu_highlight(self, index):
        scroll_idx = 0
        highlight = ((index * 10, index * 10 + 8))  # TODO replace 10
        num_visible = 3  # TODO
        if index > num_visible:
            scroll_idx = index - num_visible
        self.refresh_menu(highlight, scroll_idx * 10)

    # Parameter Value Edit
    def draw_value_edit(self, plugin_name, parameter, value):
        # Title (parameter name)
        self.images[0].paste(0, (0, 0, self.width, self.zone_height[0]))
        title = "%s-%s" % (plugin_name, parameter.name)
        self.draw[0].text((0, -2), title, True, self.title_font)
        self.refresh_zone(0)

        # Back message (zone 1)
        #self.images[1].paste(0, (0, 0, self.width, self.zone_height[1]))
        #self.draw[1].text((0, 0), "Press and hold to go back", True, self.small_bold_font)  # TODO this gets erased by graph function
        #self.refresh_zone(1)

        # Graph
        self.draw_value_edit_graph(parameter, value)

    def draw_value_edit_graph(self, parameter, value):
        self.menu_image.paste(0, (0, 0, self.width, self.menu_height))
        y0 = self.menu_y0
        y1 = y0 - 2
        yt = 16
        x = 0  # TODO offset messes scale
        xpitch = 4
        self.menu_draw.text((0, yt), "%s" % util.format_float(value), 1, self.label_font)

        val = util.renormalize(value, parameter.minimum, parameter.maximum, 0, 127)
        yref = y1
        while x < 127:  # TODO 127 minus x pitch
            self.menu_draw.line(((x + 2, y0), (x + 2, yref)), 1, 1)

            if (x < val) and (x % xpitch) == 0:
                self.menu_draw.rectangle(((x, y0), (x + 1, y1)), 1)
                y1 = y1 - 1

            x = x + xpitch
            yref = yref - 1

        self.menu_draw.text((0, self.menu_y0 + 4), "%d" % parameter.minimum, 1, self.small_font)
        self.menu_draw.text((127 - (len(str(parameter.maximum)) * 4), self.menu_y0 + 4), "%d" % parameter.maximum, 1, self.small_font)

        self.refresh_menu()

    # Zone 0 - Pedalboard and Preset
    def draw_title(self, pedalboard, preset, invert_pb, invert_pre):
        self.images[0].paste(0, (0, 0, self.width, self.zone_height[0]))

        #pedalboard = pedalboard.lower().capitalize()
        pb_size  = self.title_font.getsize(pedalboard)[0]
        font_height = self.title_font.getsize(pedalboard)[1]
        y = -2  # negative pushes text to top of LCD

        # Pedalboard Name
        if invert_pb:
            self.draw[0].rectangle(((0, y), (pb_size, font_height - 2)), True, 1)
        self.draw[0].text((0, y), pedalboard, not invert_pb, self.title_font)

        if preset != None:

            # delimiter
            delimiter = "/"
            x = pb_size + 1
            self.draw[0].text((x, y), delimiter, 1, self.title_font)

            # Preset Name
            #preset = preset.lower().capitalize()
            pre_size = self.title_font.getsize(preset)[0]
            x = x + self.title_font.getsize(delimiter)[0]
            x2 = x + pre_size
            y2 = font_height
            if invert_pre:
                self.draw[0].rectangle(((x, y), (x2, y2 - 2)), True, 1)
            self.draw[0].text((x, y), preset, not invert_pre, self.title_font)

        self.refresh_zone(0)

    # Zone 1 - Analog Assignments (Tweak, Expression Pedal, etc.)
    def draw_analog_assignments(self, controllers):
        zone = 1
        self.images[zone].paste(0, (0, 0, self.width, self.zone_height[zone]))

        # Expression Pedal assignment
        type = 'EXPRESSION'  # TODO should this be an enum
        text = "None"
        self.draw[zone].line(((0, 5), (8, 1)), True, 1)
        self.draw[zone].line(((0, 5), (8, 5)), True, 2)
        if type in controllers:  # TODO Slightly lame string linkage to controller class
            text = "%s:%s" % (self.shorten_name(controllers[type][0], self.plugin_width), controllers[type][1])
        self.draw[zone].text((10, 2), text, True, self.small_font)

        # Tweak knob assignment
        type = 'KNOB'
        text = "None"
        x = 66
        self.draw[zone].ellipse(((x, 0), (x + 6, 6)), True, 1)
        self.draw[zone].line(((x + 3, 0), (x + 3, 2)), False, 1)
        if type in controllers:
            text = "%s:%s" % (self.shorten_name(controllers[type][0], self.plugin_width), controllers[type][1])
        self.draw[zone].text((x+9, 2), text, True, self.small_font)

        self.refresh_zone(zone)

    def draw_info_message(self, text):
        zone = 1
        self.images[zone].paste(0, (0, 0, self.width, self.zone_height[zone]))
        self.draw[zone].text((0, 2), text, True, self.small_font)
        self.refresh_zone(zone)

    # Zones 2, 4, 6 - Plugin Selection
    def draw_plugin_select(self, plugin=None):
        # Clear all selection zones
        # TODO could be smarter about which zones to clear and refresh, but...
        self.images[2].paste(0, (0, 0, self.width, self.zone_height[2]))
        self.images[4].paste(0, (0, 0, self.width, self.zone_height[4]))
        self.images[6].paste(0, (0, 0, self.width, self.zone_height[6]))

        if plugin is not None:
            x = plugin.lcd_xyz[0]
            y = plugin.lcd_xyz[1]
            zone = plugin.lcd_xyz[2] - 1

            self.draw[zone].point((x+ 8, 0), True)
            self.draw[zone].point((x+ 9, 0), True)
            self.draw[zone].point((x+10, 0), True)
            self.draw[zone].point((x+11, 0), True)
            self.draw[zone].point((x+12, 0), True)
            self.draw[zone].point((x+13, 0), True)
            self.draw[zone].point((x+14, 0), True)
            self.draw[zone].point((x+15, 0), True)
            self.draw[zone].point((x+16, 0), True)

            self.draw[zone].point((x+ 9, 1), True)
            self.draw[zone].point((x+10, 1), True)
            self.draw[zone].point((x+11, 1), True)
            self.draw[zone].point((x+12, 1), True)
            self.draw[zone].point((x+13, 1), True)
            self.draw[zone].point((x+14, 1), True)
            self.draw[zone].point((x+15, 1), True)

        self.refresh_zone(2)
        self.refresh_zone(4)
        self.refresh_zone(6)

    # Zones 3, 5, 7 - Plugin Display
    def draw_box(self, xy, xy2, zone, text, round_bottom_corners=False):
        self.draw[zone].rectangle((xy, xy2), False, 1)
        self.draw[zone].point(xy)  # Round the top corners
        self.draw[zone].point((xy2[0],xy[1]))
        if round_bottom_corners:
            self.draw[zone].point((xy[0],xy2[1]))
            self.draw[zone].point((xy2[0],xy2[1]))
        self.draw[zone].text((xy[0] + 2, xy[1] + 2), text, True, self.small_font)

    def draw_plugin(self, zone, x, y, text, width, eol, plugin, round_bottom_corners=False):
        text = self.shorten_name(text, width)
        x2 = x + width
        if (eol):
            x2 = x2 - 1

        plugin.lcd_xyz = (x, y, zone)
        self.draw_box((x, y), (x2, y + self.plugin_height), zone, text, round_bottom_corners)

        bypass_indicator_xy = ((x+3, y+9), (x2-3, y+9))
        plugin.bypass_indicator_xy = bypass_indicator_xy
        self.draw[zone].line(bypass_indicator_xy, not plugin.is_bypassed(), self.plugin_bypass_thickness)

        return x2

    def draw_bound_plugins(self, plugins, footswitches):
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
                        label = p.instance_id.replace('/', "")[:self.plugin_label_length]  # TODO this replacement should be done in one place higher level
                        label = label.replace("_", "")
                    self.draw_plugin(7, self.footswitch_xy[fs_id][0], self.footswitch_xy[fs_id][1], label,
                                     self.footswitch_width, False, p, True)

        # Draw any footswitches which weren't found to be bound to a plugin
        for fs_id in range(len(fss)):
            if fss[fs_id] is None:
                continue
            label = "" if fss[fs_id].display_label is None else fss[fs_id].display_label
            xy2 = (self.footswitch_xy[fs_id][0] + self.footswitch_width, self.footswitch_xy[fs_id][1] + self.plugin_height)
            self.draw_box((self.footswitch_xy[fs_id][0], self.footswitch_xy[fs_id][1]), xy2, 7, label, True)

        self.refresh_zone(7)

    def draw_plugins(self, plugins):
        y = 0
        x = 0
        xwrap = 110  # scroll if exceeds this width
        ymax = 64  # Maximum y for plugin LCD zone
        rect_x_pad = 2
        zone = 3
        self.images[3].paste(0, (0, 0, self.width, self.zone_height[3]))
        self.images[5].paste(0, (0, 0, self.width, self.zone_height[5]))

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
            x = x + rect_x_pad
            if x > xwrap:
                zone += 2
                x = 0
                if y >= ymax:
                    break  # Only display 2 rows, huge pedalboards won't fully render  # TODO make sure this works
        self.refresh_plugins()

    def shorten_name(self, name, width):
        text = ""
        for x in name.lower().replace('_', '').replace('/', ''):
            test = text + x
            test_size = self.small_font.getsize(test)[0]
            if test_size >= width:
                break
            text = test
        return text
