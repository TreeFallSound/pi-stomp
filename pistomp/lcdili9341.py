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

import board
import digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.ili9341 as ili9341
import pistomp.lcdcolor as lcdcolor

# The code in this file should generally be specific to initializing a specific display and rendering (and refreshing)
# Most draw methods should be implemented in the parent class unless that needs to be overriden for this display
# All __init__ parameters from the lcdbase.py should be specified in this __init__


class Lcd(lcdcolor.Lcdcolor):

    def __init__(self, cwd):
        super(Lcd, self).__init__(cwd)

        # Configuration for CS and DC pins (these are FeatherWing defaults on M0/M4):
        cs_pin = digitalio.DigitalInOut(board.CE0)
        dc_pin = digitalio.DigitalInOut(board.D6)
        reset_pin = digitalio.DigitalInOut(board.D5)

        # Config for display baudrate (default max is 24mhz):
        BAUDRATE = 64000000

        # Setup SPI bus using hardware SPI:
        spi = board.SPI()

        # Create the ST7789 display:
        self.disp = ili9341.ILI9341(
            spi,
            cs=cs_pin,
            dc=dc_pin,
            rst=reset_pin,
            baudrate=BAUDRATE,
            width=240,
            height=320
        )

        # Fonts
        self.title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
        self.splash_font = ImageFont.truetype('DejaVuSans.ttf', 40)
        self.small_font = ImageFont.truetype("DejaVuSans.ttf", 18)
        #self.small_font = ImageFont.truetype(os.path.join(cwd, "fonts", "EtBt6001-JO47.ttf"), 11)

        # Colors
        self.background = (0, 0, 0)
        self.foreground = (255, 255, 255)
        self.highlight = (255, 0, 0)
        self.color_plugin = (100, 100, 240)
        self.color_plugin_bypassed = (80, 80, 80)

        # Width and height exchanged for 90 degree rotation during render/refresh
        self.width = self.disp.height
        self.height = self.disp.width
        self.top = 0
        self.left = 2

        # Zone dimensions
        self.zones = 8
        self.zone_height = {0: 38,
                            1: 30,
                            2: 2,
                            3: 30,
                            4: 2,
                            5: 30,
                            6: 48,
                            7: 60}

        self.footswitch_xy = {0: (0, 0, (255, 255, 255)),
                              1: (120, 0, (0, 255, 0)),
                              2: (240, 0, (0, 0, 255))}

        # Element dimensions
        self.plugin_height = 22
        self.plugin_width = 56
        self.plugin_width_medium = 70
        self.plugin_rect_x_pad = 5
        self.plugin_bypass_thickness = 2
        self.plugin_label_length = 7
        self.footswitch_width = 70
        self.footswitch_ring_width = 5

        self.images = [Image.new('RGB', (self.width, self.zone_height[0])),  # Pedalboard / Preset Title bar
                       Image.new('RGB', (self.width, self.zone_height[1])),  # Analog Controllers
                       Image.new('RGB', (self.width, self.zone_height[2])),  # Plugin selection
                       Image.new('RGB', (self.width, self.zone_height[3])),  # Plugins Row 1
                       Image.new('RGB', (self.width, self.zone_height[4])),  # Plugin selection
                       Image.new('RGB', (self.width, self.zone_height[5])),  # Plugins Row 2
                       Image.new('RGB', (self.width, self.zone_height[6])),  # Plugin selection
                       Image.new('RGB', (self.width, self.zone_height[7]))]  # Footswitch Plugins

        self.draw = [ImageDraw.Draw(self.images[0]), ImageDraw.Draw(self.images[1]),
                     ImageDraw.Draw(self.images[2]), ImageDraw.Draw(self.images[3]),
                     ImageDraw.Draw(self.images[4]), ImageDraw.Draw(self.images[5]),
                     ImageDraw.Draw(self.images[6]), ImageDraw.Draw(self.images[7])]

        self.check_vars_set()

    def refresh_plugins(self):
        # TODO could be smarter here and only refresh the affected zone
        self.refresh_zone(2)
        self.refresh_zone(4)
        self.refresh_zone(6)
        self.refresh_zone(7)
        self.refresh_zone(5)
        self.refresh_zone(3)

    def refresh_zone(self, zone_idx):
        # Determine the start y position by adding the height of all previous zones
        # TODO this shouldn't be calculated each time
        y_offset = 0
        for i in range(zone_idx):
            y_offset += self.zone_height[i]
        self.disp.image(self.images[zone_idx], 90, x=y_offset, y=0)

    def set_pixel(self, x, y, value):
        pass

    def splash_show(self):
        return
        self.clear()
        self.draw.text((0, self.top + 30), "pi Stomp!", font=self.splash_font, fill=(255, 255, 255))
        self.refresh()

    def cleanup(self):
        self.clear()

    def clear(self):
        self.disp.fill(0)