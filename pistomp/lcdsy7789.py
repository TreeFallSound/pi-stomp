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

from abc import ABC, abstractmethod

import board
#from board import SCL, SDA
import busio
import digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789

import ST7789

class Lcd(ABC):

    def __init__(self):

        # Create ST7789 LCD display class.
        self.disp = ST7789.ST7789(
            port=0,
            cs=ST7789.BG_SPI_CS_BACK,  # BG_SPI_CSB_BACK or BG_SPI_CS_FRONT
            dc=1,
            backlight=18,  # 18 for back BG slot, 19 for front BG slot.
            width=240,
            height=135,
            rotation=0,
            spi_speed_hz=80 * 1000 * 1000
        )

        # Create blank image for drawing.
        # Make sure to create image with mode '1' for 1-bit color.
        self.width = self.disp.width
        self.height = self.disp.height

        padding = 50
        self.top = padding
        self.bottom = self.height - padding
        self.left = padding
        self.image = Image.new("RGB", (self.height, self.width))

        # Get drawing object to draw on image.
        self.draw = ImageDraw.Draw(self.image)

        # Draw a black filled box to clear the image.
        self.draw.rectangle((0, 0, self.height, self.width), outline=0, fill=0)

        # Font
        self.font_size = 26
        self.font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', self.font_size)
        self.splash_font_size = 40
        self.splash_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', self.splash_font_size)

        # Turn on the backlight
        backlight = digitalio.DigitalInOut(board.D22)
        backlight.switch_to_output()
        backlight.value = True
        self.splash_show()

    def refresh(self):
        self.disp.display(self.image)

    def splash_show(self):
        self.clear()
        self.draw.text((self.left + 10, self.top + 70), "pi Stomp!", font=self.splash_font, fill=255)
        self.refresh()

    def cleanup(self):
        self.clear()

    def clear(self):
        self.draw.rectangle((0, 0, self.height, self.width), outline=0, fill=(0, 0, 0))
        self.disp.display(self.image)

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
