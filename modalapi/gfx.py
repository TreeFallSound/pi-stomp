#!/usr/bin/env python

import signal
import spidev

from gfxhat import touch, lcd, backlight, fonts
from PIL import Image, ImageFont, ImageDraw


class Gfx:

    def __init__(self):   # TODO make a singleton

        self.width, self.height = lcd.dimensions()
        self.image = Image.new('P', (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)

        # Load fonts
        self.font = ImageFont.truetype("DejaVuSans-Bold.ttf", 12)
        self.label_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 10)
        self.small_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 9)

        self.refresh_needed = True
        self.enable_backlight()

    def refresh(self):
        flipped = self.image.transpose(Image.ROTATE_180)   # use 'flipped' instead of 'image' below
        for x in range(self.width):
            for y in range(self.height):
                pixel = flipped.getpixel((x, y))
                lcd.set_pixel(x, y, pixel)
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

    def clear(self):
        for x in range(6):
            backlight.set_pixel(x, 0, 0, 0)
            touch.set_led(x, 0)
        backlight.show()
        lcd.clear()
        lcd.show()

    def draw_text_rows(self, text):
        self.image.paste(0, (0, 0, self.width, self.height))
        #self.draw.text((0, 0), text, 1, self.font)
        self.draw.text((0, 0), 'PoorSugar - Verse', 1, self.font)

        # line_y = 15
        # for p in pl:
        #     draw.text((0, line_y), "< " + p, 1, label_font)
        #     line_y = line_y + 11

        self.refresh_needed = True
        self.refresh()

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





# def readChannel(channel):
#     adc = spi.xfer2([1, (8+channel) << 4, 0])
#     data = ((adc[1]&3) << 8) + adc[2]
#     return data
#
# try:
#     #signal.pause()
#     gfx = Gfx()
#     while True:
#         #print("data %d" % readChannel(0))
#         #data = readChannel(0)
#         #print("data %d" % data)
#         gfx.text("blah")
#         time.sleep(0.1)
#
# except KeyboardInterrupt:
#     gfx.clear()

