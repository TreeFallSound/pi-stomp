#!/usr/bin/env python

import signal
import spidev

from gfxhat import touch, lcd, backlight, fonts
from PIL import Image, ImageFont, ImageDraw


class Gfx:

    def __init__(self):   # TODO make a singleton

        self.width, self.height = lcd.dimensions()

        # Zone dimensions (flipped 180 degrees)
        #               ((x0, y0), (x1, y1))
        self.zone = {0: ((0, 49), (128, 64)),  # Top
                     1: ((0, 19), (128, 48)),  # Mid
                     2: ((0, 0),  (128, 18))}  # Bot

        # Element dimensions
        self.plugin_height = 11
        self.plugin_width = 23
        self.plugin_bypass_thickness = 2

        self.image = Image.new('P', (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)
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
        flipped = self.image.transpose(Image.ROTATE_180)
        #flipped = self.image
        for x in range(self.zone[zone_idx][0][0], self.zone[zone_idx][1][0]):
            for y in range(self.zone[zone_idx][0][1], self.zone[zone_idx][1][1]):
                pixel = flipped.getpixel((x, y))
                lcd.set_pixel(x, y, pixel)
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
        self.image.paste(0, (0, 0, self.width, self.height))
        self.draw.text((0, 0), text, 1, self.title_font)
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
        self.draw_footswitches()  # TODO not here
        self.refresh()

    def shorten_name(self, name):
        text = ""
        for x in name.lower():
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

    def draw_plugin(self, x, y, text, expand_rect, plugin):
        if expand_rect:
            text_size = self.small_font.getsize(text)[0]
            x2 = x + text_size + 2
        else:
            text = self.shorten_name(text)
            x2 = x + self.plugin_width

        fill = False
        self.draw.rectangle(((x, y), (x2, y + self.plugin_height)), fill, 1)
        self.draw.text((x + 1, y + 1), text, not fill, self.small_font)
        bypass_indicator_xy = ((x+2, y+9), (x2-2, y+9))
        plugin.bypass_indicator_xy = bypass_indicator_xy
        self.draw.line(bypass_indicator_xy, not plugin.bypassed, self.plugin_bypass_thickness)
        return x2

    def draw_plugins(self, plugins):
        # TODO don't hardcode numbers by assuming 128x64, use width and height
        # TODO Improve expansion/wrapping algorithm (calculate values)
        y = 16
        x = 0
        xwrap = 100  # scroll if exceeds this width
        ymax = 48  # Maximum y for plugin LCD zone
        expand_rect = len(plugins) <= 5
        rect_x_pad = 2
        rect_y_pitch = 15
        max_label_length = 7
        for p in reversed(plugins):
            label = p.instance_id.replace('/', "")[:max_label_length]
            x = self.draw_plugin(x, y, label, expand_rect, p)
            x = x + rect_x_pad
            if x > xwrap:
                x = 0
                y = y + rect_y_pitch
                if y >= ymax:
                    break  # Only display 2 rows, huge pedalboards won't fully render
        #self.refresh()

        # Draw bypass (enable) indicator
        # Set pixels directly instead of drawing on an image
        # for p in plugins:
        #     print("pl: %s" % p.instance_id)
        #     self.redraw_bypass(p, p.bypassed)
        #     #if not p.bypassed:
        #     #    self.redraw_bypass(p, not p.bypassed)


    def draw_footswitch(self, index, text, enabled):
        y0 = 38
        y1 = 63
        x0 = 42 * index
        x1 = x0 + 40
        self.draw.ellipse(((x0, y0), (x1, y1)), enabled, 1)
        self.draw.text((x0 + 2, y0 + 8), text, not enabled, self.small_font)


    def draw_footswitches(self):
        self.draw_footswitch(0, "Dist", 1)
        self.draw_footswitch(1, "Chorus", 0)
        self.draw_footswitch(2, "Delay", 0)
