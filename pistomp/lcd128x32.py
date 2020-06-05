#!/usr/bin/env python

from abc import ABC, abstractmethod

from board import SCL, SDA
import busio
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306

class Lcd(ABC):

    def __init__(self):
        # Create the I2C interface.
        i2c = busio.I2C(SCL, SDA)

        # Create the SSD1306 OLED class.
        # The first two parameters are the pixel width and pixel height.  Change these
        # to the right size for your display!
        self.disp = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c)

        # Create blank image for drawing.
        # Make sure to create image with mode '1' for 1-bit color.
        self.width = self.disp.width
        self.height = self.disp.height

        padding = -4
        self.top = padding
        self.bottom = self.height - padding
        self.image = Image.new("1", (self.width, self.height))

        # Get drawing object to draw on image.
        self.draw = ImageDraw.Draw(self.image)

        # Draw a black filled box to clear the image.
        self.draw.rectangle((0, 0, self.width, self.height), outline=0, fill=0)

        # Font
        self.font_size = 18
        self.font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', self.font_size)
        self.splash_font_size = 26
        self.splash_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', self.splash_font_size)

        self.splash_show()

    def refresh(self):
        self.disp.image(self.image)
        self.disp.show()

    def splash_show(self):
        self.clear()
        self.draw.text((0, self.top + 0), "pi Stomp!", font=self.splash_font, fill=255)
        self.refresh()

    def cleanup(self):
        self.clear()

    def clear(self):
        self.draw.rectangle((0, 0, self.width, self.height), outline=0, fill=0)
        self.disp.show()

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
