#!/usr/bin/env python3

from abc import ABC, abstractmethod

import board
import busio
import digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789


class Lcd(ABC):

    def __init__(self):
        # Configuration for CS and DC pins (these are FeatherWing defaults on M0/M4):
        cs_pin = digitalio.DigitalInOut(board.CE0)
        dc_pin = digitalio.DigitalInOut(board.D1)
        reset_pin = None

        # Config for display baudrate (default max is 24mhz):
        BAUDRATE = 64000000

        # Setup SPI bus using hardware SPI:
        spi = board.SPI()

        # Create the ST7789 display:
        self.disp = st7789.ST7789(
            spi,
            cs=cs_pin,
            dc=dc_pin,
            rst=reset_pin,
            baudrate=BAUDRATE,
            width=135,
            height=240,
            x_offset=53,
            y_offset=40,
        )

        # Create blank image for drawing.
        # Make sure to create image with mode '1' for 1-bit color.
        self.width = self.disp.width - 1
        self.height = self.disp.height - 1

        padding = 0
        self.top = padding
        self.bottom = self.height - padding
        self.image = Image.new("RGB", (self.height, self.width))

        # Get drawing object to draw on image.
        self.draw = ImageDraw.Draw(self.image)

        # Draw a black filled box to clear the image.
        #self.draw.rectangle((0, 0, self.height, self.width), outline=0, fill=0)

        # Font
        self.font_size = 30
        self.font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', self.font_size)
        self.splash_font_size = 40
        self.splash_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', self.splash_font_size)

        # Splash
        self.splash_show()

    def refresh(self):
        self.disp.image(self.image, 90)

    def splash_show(self):
        self.clear()
        self.draw.text((0, self.top + 30), "pi Stomp!", font=self.splash_font, fill=(255, 255, 255))
        self.refresh()

    def cleanup(self):
        self.clear()

    def clear(self):
        self.draw.rectangle((0, 0, self.height, self.width), outline=0, fill=(255, 255, 255))
        self.disp.image(self.image, 90)

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
        x = 0
        self.clear()
        self.draw.text((x, self.top), pedalboard, font=self.font, fill=255)
        self.draw.text((x, self.top + self.font_size), preset, font=self.font, fill=255)

        x = 5
        y = 70
        square = 30
        pitch = 10
        self.draw.rectangle((x, y, x + square, y + square), outline=0, fill=(200, 0, 0))
        x = x + square + pitch
        self.draw.rectangle((x, y, x + square, y + square), outline=(0, 200, 0), fill=(255, 255, 255))
        x = x + square + pitch
        self.draw.rectangle((x, y, x + square, y + square), outline=1, fill=(0, 0, 200))


        self.refresh()

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

    def draw_plugins(self, plugins):
        pass
