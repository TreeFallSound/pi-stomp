#!/usr/bin/env python

import signal
import spidev

from modalapi.footswitch import Footswitch

from gfxhat import touch, lcd, backlight, fonts
from PIL import Image, ImageFont, ImageDraw


class Gfx:

    def __init__(self):   # TODO make a singleton

        self.width, self.height = lcd.dimensions()

        # Zone dimensions
        self.zone_height = {0: 13,
                            1: 8,
                            2: 2,
                            3: 12,
                            4: 2,
                            5: 13,
                            6: 2,
                            7: 12}

        self.footswitch_xy = {0: (0,   0),
                              1: (52,  0),
                              2: (103, 0)}

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


        self.enable_backlight()

        # Load fonts
        self.title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 11)
        self.label_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 10)
        self.small_font = ImageFont.truetype("DejaVuSans.ttf", 8)

        self.refresh_needed = True
        self.num_leds = 6

    def refresh(self):
        flipped = self.image.transpose(Image.ROTATE_180)
        for x in range(self.width):
            for y in range(self.height):
                pixel = flipped.getpixel((x, y))
                lcd.set_pixel(x, y, pixel)
        lcd.show()
        self.refresh_needed = False

    def flip_coordinates(self, coords):
        xy0 = (self.width - coords[1][0], self.height - 1 - coords[1][1])
        xy1 = (self.width - coords[0][0], self.height - 1 - coords[0][1])
        ret = (xy0, xy1)
        return ret

    def refresh_zone(self, zone_idx):
        #flipped = self.images[zone_idx].transpose(Image.ROTATE_180)
        flipped = self.images[zone_idx]
        y_offset = 1 if (zone_idx == 0) else 0
        for i in range(zone_idx):
            y_offset += self.zone_height[i]
        for x in range(0, self.width):
            for y in range(0, self.zone_height[zone_idx]):
                pixel = flipped.getpixel((x, y))
                lcd.set_pixel(self.width - x - 1, self.height - y - y_offset, pixel)
                #print("%d %d" % (self.width - x - 1, self.height - y - y_offset))
        lcd.show()
        self.refresh_needed = False

    def refresh_area(self, xy, bypassed):
        #flipped = self.image.transpose(Image.ROTATE_180)
        flipped = self.image
        print(xy)
        coords = self.flip_coordinates(xy)
        print(coords)
        for x in range(coords[0][0], coords[1][0]):
            for y in range(coords[0][1], coords[1][1]):
                print("x %d  y %d" % (x, y))
                #pixel = flipped.getpixel((x, y))
                lcd.set_pixel(x, y, not bypassed)
        lcd.show()
        self.refresh_needed = False

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

    def draw_title(self, text):
        self.images[0].paste(0, (0, 0, self.width, self.zone_height[0]))
        self.draw[0].text((0, -1), text, 1, self.title_font)  # -1 pushes text to very top of LCD
        self.refresh_needed = True
        #self.refresh()

    def draw_bargraph(self, val):
        # TODO don't hardcode numbers by assuming 128x64, use width and height
        # Don't hardcode 127
        #self.image.paste(0, (0, 0, self.width, self.height))
        y0 = 32
        y1 = y0 - 2
        yt = 16
        x = 40  # TODO ofset messes scale
        val = min(val, 127)  # Scale to 127  TODO define max midi
        # TODO scale to 100 (as in, percent)

        self.draw.text((0, yt), "Gain", 1, self.label_font)
        self.draw.text((40, yt), str(val), 1, self.label_font)

        while x < val:
            self.draw.rectangle(((x, y0), (x + 1, y1)), 1)
            if x >= 127:
                break
            if (x % 9) == 0:
                y1 = y1 - 1
                x = x + 3
            else:
                x = x + 1

        self.refresh_needed = True
        self.refresh()

    def shorten_name(self, name):
        text = ""
        for x in name.lower().replace('_', ''):
            test = text + x
            test_size = self.small_font.getsize(test)[0]
            if test_size >= self.plugin_width:
                break
            text = test
        return text

    def redraw_bypass(self, plugin, bypassed):
        xy = plugin.bypass_indicator_xy
        print(xy)
        #self.draw.line(xy, not bypassed, self.plugin_bypass_thickness)
        self.refresh_area(xy, bypassed)

    def draw_plugin_select(self, plugin):
        x = plugin.lcd_xyz[0]
        y = plugin.lcd_xyz[1]
        zone = plugin.lcd_xyz[2] - 1

        # Clear all selection zones
        self.images[2].paste(0, (0, 0, self.width, self.zone_height[2]))
        self.images[4].paste(0, (0, 0, self.width, self.zone_height[4]))
        self.images[6].paste(0, (0, 0, self.width, self.zone_height[6]))

        self.draw[zone].point((x+11, 0), True)
        self.draw[zone].point((x+12, 0), True)
        self.draw[zone].point((x+13, 0), True)
        self.draw[zone].point((x+14, 0), True)
        self.draw[zone].point((x+12, 1), True)
        self.draw[zone].point((x+13, 1), True)

        self.refresh_zone(2)
        self.refresh_zone(4)
        self.refresh_zone(6)


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
        for p in plugins:
            if p.has_footswitch is False:
                continue
            label = p.instance_id.replace('/', "")[:self.plugin_label_length]
            for c in p.controllers:
                if isinstance(c, Footswitch):
                    fs_id = c.id
                    self.draw_plugin(7, self.footswitch_xy[fs_id][0], self.footswitch_xy[fs_id][1], label, False, p)

    def draw_plugins(self, plugins):
        # TODO don't hardcode numbers by assuming 128x64, use width and height
        # TODO Improve expansion/wrapping algorithm (calculate values)
        y = 0
        x = 0
        xwrap = 110  # scroll if exceeds this width
        ymax = 64  # Maximum y for plugin LCD zone
        expand_rect = len(plugins) <= 5
        rect_x_pad = 2
        rect_y_pitch = 15
        count = 0
        zone = 3
        self.images[zone].paste(0, (0, 0, self.width, self.zone_height[zone]))
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
                #y = y + rect_y_pitch
                if y >= ymax:
                    break  # Only display 2 rows, huge pedalboards won't fully render

        zone = 1
        self.draw[zone].line(((0, 5), (8, 1)), True, 1)
        self.draw[zone].line(((0, 5), (8, 5)), True, 2)
        self.draw[zone].text((10, 0), "delay:time", True, self.small_font)


        self.draw[zone].ellipse(((66,0), (72,6)), True, 1)
        self.draw[zone].line(((69, 0), (69, 2)), False, 1)
        self.draw[zone].text((75, 0), "ts9:drive", True, self.small_font)


        #self.draw_plugin(3, 0, 0, "foo1", True, plugins[0])
        #self.draw_plugin(3, 52, 0, "foo2", True, plugins[0])
       # self.draw_plugin(3, 105, 0, "foo3", True, plugins[0])
        #self.refresh()

        # Draw bypass (enable) indicator
        # Set pixels directly instead of drawing on an image
        # for p in plugins:
        #     print("pl: %s" % p.instance_id)
        #     self.redraw_bypass(p, p.bypassed)
        #     #if not p.bypassed:
        #     #    self.redraw_bypass(p, not p.bypassed)
