#!/usr/bin/env python

import signal
import spidev

from gfxhat import touch, lcd, backlight, fonts
from PIL import Image, ImageFont, ImageDraw

from modalapi.footswitch import Footswitch  # TODO would like to avoid this module knowing such details

class Gfx:

    def __init__(self):   # TODO make a singleton

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
                              1: (52,  0),
                              2: (103, 0)}


        self.deep_edit_height = self.height - self.zone_height[0] + 1  # TODO figure out why +1
        self.deep_edit_image_height = self.deep_edit_height * 2
        self.deep_edit_image = Image.new('L', (self.width, self.deep_edit_image_height))  # TODO enough height?
        self.deep_edit_draw = ImageDraw.Draw(self.deep_edit_image)

        # Element dimensions
        self.plugin_height = 11
        self.plugin_width = 24
        self.plugin_bypass_thickness = 2
        self.plugin_label_length = 7

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
        self.title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 11)
        self.label_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 10)  # TODO get rid
        self.small_bold_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 8)
        self.small_font = ImageFont.truetype("DejaVuSans.ttf", 8)

        # Turn on Backlight
        self.enable_backlight()

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
                #print("%d %d" % (self.width - x - 1, self.height - y - y_offset))
        lcd.show()

    def refresh_deep_edit(self, highlight_range=None, scroll_offset=0):
        # Set Pixels
        y_offset = self.zone_height[0]
        for x in range(0, self.width):
            for y in range(0, self.deep_edit_height):
                y_draw = y + scroll_offset
                pixel = self.deep_edit_image.getpixel((x, y_draw))
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

    # Deep Edit Screens
    def draw_deep_edit(self, plugin_name, parameters):
        # Title (plugin name)
        self.images[0].paste(0, (0, 0, self.width, self.zone_height[0]))
        self.draw[0].text((0, 0), plugin_name, True, self.title_font)
        self.refresh_zone(0)

        # Back button (index 0)
        self.deep_edit_image.paste(0, (0, 0, self.width, self.deep_edit_height))
        self.deep_edit_draw.text((0, 0), "< Back to main screen", True, self.small_bold_font)

        # Plugin Parameters
        idx = 1
        x = 8
        y = 10  # TODO Define this somewhere
        for p in parameters:
            self.deep_edit_draw.text((x, y), "%d %s" % (idx, p.name), True, self.small_font)
            y += 10
            idx += 1
        self.refresh_deep_edit()

    def draw_deep_edit_hightlight(self, highlight_idx):
        scroll_idx = 0
        highlight = ((highlight_idx * 10, highlight_idx * 10 + 8))  # TODO replace 10
        num_visible = 3  # TODO
        if highlight_idx > num_visible:
            scroll_idx = highlight_idx - num_visible
        self.refresh_deep_edit(highlight, scroll_idx * 10)

    def remap_range(self, value, left_min, left_max, right_min, right_max):
        # this remaps a value from original (left) range to new (right) range
        # Figure out how 'wide' each range is
        left_span = left_max - left_min
        right_span = right_max - right_min

        # Convert the left range into a 0-1 range (int)
        valueScaled = int(value - left_min) / int(left_span)

        # Convert the 0-1 range into a value in the right range.
        return int(right_min + (valueScaled * right_span))

    def draw_value_edit(self, plugin_name, parameter, value):
        # Title (parameter name)
        self.images[0].paste(0, (0, 0, self.width, self.zone_height[0]))
        title = "%s-%s" % (plugin_name, parameter.name)
        self.draw[0].text((0, 0), title, True, self.label_font)
        self.refresh_zone(0)

        # Back button (index 0)
        self.deep_edit_image.paste(0, (0, 0, self.width, self.deep_edit_height))
        self.deep_edit_draw.text((0, 0), "Press and hold to go back", True, self.small_bold_font)

        # Parameter details
        #self.image.paste(0, (0, 0, self.width, self.height))
        y0 = 40
        y1 = y0 - 2
        yt = 16
        x = 0  # TODO ofset messes scale
        #val = min(parameter.value, 127)  # Scale to 127  TODO define max midi
        # TODO scale to 100 (as in, percent)

        #self.deep_edit_draw.text((0, yt), "Gain", 1, self.label_font)
        #self.deep_edit_draw.text((40, yt), str(val), 1, self.label_font)

        val = self.remap_range(value, parameter.minimum, parameter.maximum, 0, 127)
        self.deep_edit_draw.text((0, yt), str(val), 1, self.label_font)

        while x < val:
            self.deep_edit_draw.rectangle(((x, y0), (x + 1, y1)), 1)
            if x >= 127:
                break
            if (x % 9) == 0:
                y1 = y1 - 1
                x = x + 3
            else:
                x = x + 1

        self.refresh_deep_edit()

    def draw_value_edit_graph(self, parameter, value):  # TODO XXX share this graph drawing stuff
        self.deep_edit_image.paste(0, (0, 0, self.width, self.deep_edit_height))
        y0 = 40
        y1 = y0 - 2
        yt = 16
        x = 0  # TODO ofset messes scale
        # val = min(parameter.value, 127)  # Scale to 127  TODO define max midi
        # TODO scale to 100 (as in, percent)

        # self.deep_edit_draw.text((0, yt), "Gain", 1, self.label_font)
        # self.deep_edit_draw.text((40, yt), str(val), 1, self.label_font)
        #print("min %d   max %d" % (parameter.minimum, parameter.maximum))
        val = self.remap_range(value, parameter.minimum, parameter.maximum, 0, 127)
        self.deep_edit_draw.text((0, yt), str(val), 1, self.label_font)

        while x < val:
            self.deep_edit_draw.rectangle(((x, y0), (x + 1, y1)), 1)
            if x >= 127:
                break
            if (x % 9) == 0:
                y1 = y1 - 1
                x = x + 3
            else:
                x = x + 1

        self.refresh_deep_edit()


    # Zone 0 - Pedalboard and Preset
    def draw_title(self, pedalboard, preset, invert_pb, invert_pre):
        self.images[0].paste(0, (0, 0, self.width, self.zone_height[0]))

        pedalboard = pedalboard.lower().capitalize()
        pb_size  = self.title_font.getsize(pedalboard)[0]
        font_height = self.title_font.getsize(pedalboard)[1]
        y = -1  # -1 pushes text to very top of LCD

        # Pedalboard Name
        if invert_pb:
            self.draw[0].rectangle(((0, y), (pb_size, font_height)), True, 1)
        self.draw[0].text((0, y), pedalboard, not invert_pb, self.title_font)

        if preset != None:

            # delimiter
            delimiter = "-"
            x = pb_size + 1
            self.draw[0].text((x, y), delimiter, 1, self.title_font)

            # Preset Name
            preset = preset.lower().capitalize()
            pre_size = self.title_font.getsize(preset)[0]
            x = x + self.title_font.getsize(delimiter)[0]
            x2 = x + pre_size
            y2 = font_height
            if invert_pre:
                self.draw[0].rectangle(((x, y), (x2, y2)), True, 1)
            self.draw[0].text((x, y), preset, not invert_pre, self.title_font)

        self.refresh_zone(0)

    # Zone 1 - Analog Assignments (Tweak, Expression Pedal, etc.)
    def draw_analog_assignments(self, controllers):
        zone = 1
        self.images[zone].paste(0, (0, 0, self.width, self.zone_height[zone]))

        text = "None"
        self.draw[zone].line(((0, 5), (8, 1)), True, 1)
        self.draw[zone].line(((0, 5), (8, 5)), True, 2)
        type = 'EXPRESSION'
        if type in controllers:  # TODO Slightly lame string linkage to controller class
            text = "%s:%s" % (self.shorten_name(controllers[type][0]), controllers[type][1])
        self.draw[zone].text((10, 0), text, True, self.small_font)

        text = "None"
        x = 66
        self.draw[zone].ellipse(((x, 0), (x + 6, 6)), True, 1)
        self.draw[zone].line(((x + 3, 0), (x + 3, 2)), False, 1)
        type = 'KNOB'
        if type in controllers:
            text = "%s:%s" % (self.shorten_name(controllers[type][0]), controllers[type][1])
        self.draw[zone].text((x+9, 0), text, True, self.small_font)

        self.refresh_zone(zone)

    def draw_info_message(self, text):
        zone = 1
        self.images[zone].paste(0, (0, 0, self.width, self.zone_height[zone]))
        self.draw[zone].text((0, 0), text, True, self.small_font)
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

            self.draw[zone].point((x+10, 0), True)
            self.draw[zone].point((x+11, 0), True)
            self.draw[zone].point((x+12, 0), True)
            self.draw[zone].point((x+13, 0), True)
            self.draw[zone].point((x+14, 0), True)
            self.draw[zone].point((x+11, 1), True)
            self.draw[zone].point((x+12, 1), True)
            self.draw[zone].point((x+13, 1), True)

        self.refresh_zone(2)
        self.refresh_zone(4)
        self.refresh_zone(6)

    # Zones 3, 5, 7 - Plugin Display
    def draw_plugin(self, zone, x, y, text, expand_rect, plugin):
        if expand_rect >= 1:
            text_size = self.small_font.getsize(text)[0]
            x2 = x + text_size + 2
        elif expand_rect <= -1:
            text = self.shorten_name(text)
            x2 = x + self.plugin_width - 1
        else:
            text = self.shorten_name(text)
            x2 = x + self.plugin_width

        fill = False
        plugin.lcd_xyz = (x, y, zone)
        self.draw[zone].rectangle(((x, y), (x2, y + self.plugin_height)), fill, 1)
        self.draw[zone].point((x,y))  # Round the top corners
        self.draw[zone].point((x2,y))

        self.draw[zone].text((x + 1, y + 1), text, not fill, self.small_font)

        bypass_indicator_xy = ((x+3, y+9), (x2-3, y+9))
        plugin.bypass_indicator_xy = bypass_indicator_xy
        self.draw[zone].line(bypass_indicator_xy, not plugin.is_bypassed(), self.plugin_bypass_thickness)

        return x2

    def draw_bound_plugins(self, plugins):
        self.images[7].paste(0, (0, 0, self.width, self.zone_height[7]))
        for p in plugins:
            if p.has_footswitch is False:
                continue
            label = p.instance_id.replace('/', "")[:self.plugin_label_length]
            for c in p.controllers:
                if isinstance(c, Footswitch):
                    fs_id = c.id
                    self.draw_plugin(7, self.footswitch_xy[fs_id][0], self.footswitch_xy[fs_id][1], label, False, p)
        self.refresh_zone(7)

    def draw_plugins(self, plugins):
        # TODO Improve expansion/wrapping algorithm (calculate values)
        y = 0
        x = 0
        xwrap = 110  # scroll if exceeds this width
        ymax = 64  # Maximum y for plugin LCD zone
        expand_rect = len(plugins) <= 5
        rect_x_pad = 2
        count = 0
        zone = 3
        self.images[3].paste(0, (0, 0, self.width, self.zone_height[3]))
        self.images[5].paste(0, (0, 0, self.width, self.zone_height[5]))
        for p in reversed(plugins):
            if p.has_footswitch:
                continue
            label = p.instance_id.replace('/', "")[:self.plugin_label_length]
            count += 1
            if count > 4:  # LAME
                expand_rect = -1
                count = 0
            x = self.draw_plugin(zone, x, y, label, expand_rect, p)
            x = x + rect_x_pad
            if x > xwrap:
                zone += 2
                x = 0
                if y >= ymax:
                    break  # Only display 2 rows, huge pedalboards won't fully render  # TODO make sure this works
        self.refresh_plugins()

    def shorten_name(self, name):
        text = ""
        for x in name.lower().replace('_', '').replace('/', ''):
            test = text + x
            test_size = self.small_font.getsize(test)[0]
            if test_size >= self.plugin_width:
                break
            text = test
        return text