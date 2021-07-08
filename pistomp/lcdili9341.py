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
import time

# The code in this file should generally be specific to initializing a specific display and rendering (and refreshing)
# Most draw methods should be implemented in the parent class unless that needs to be overriden for this display
# All __init__ parameters from the lcdbase.py should be specified in this __init__


class Lcd(lcdcolor.Lcdcolor):

    def __init__(self, cwd):
        super(Lcd, self).__init__(cwd)

        # Pin Configuration
        self.cs_pin = digitalio.DigitalInOut(board.CE0)
        self.dc_pin = digitalio.DigitalInOut(board.D6)
        self.reset_pin = digitalio.DigitalInOut(board.D5)

        # Config for display baudrate (default max is 24mhz)
        # Should agree with the SPI rate used in hardware.py for the ADC
        self.baudrate = 24000000

        # Init SPI and display
        self.spi = None
        self.disp = None
        self.init_spi_display()

        # Fonts
        self.title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
        self.splash_font = ImageFont.truetype('DejaVuSans.ttf', 40)
        self.small_font = ImageFont.truetype("DejaVuSans.ttf", 18)
        #self.small_font = ImageFont.truetype(os.path.join(cwd, "fonts", "EtBt6001-JO47.ttf"), 11)

        # Colors
        self.background = (0, 0, 0)
        self.foreground = (255, 255, 255)
        self.highlight = (255, 255, 0)
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
                            1: 32,
                            2: 0,
                            3: 32,
                            4: 0,
                            5: 80,
                            6: 0,
                            7: 58}
        self.zone_y = {}
        self.flip = True  # Flip the LCD vertically
        self.calc_zone_y()

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
        self.lock = False

    def init_spi_display(self):
        self.spi = board.SPI()
        spi = self.spi
        cs = self.cs_pin
        dc = self.dc_pin
        rst = self.reset_pin
        baud = self.baudrate

        self.disp = ili9341.ILI9341(
            spi,
            cs=cs,
            dc=dc,
            rst=rst,
            baudrate=baud
        )

    def refresh_plugins(self):
        # TODO could be smarter here and only refresh the affected zone
        self.refresh_zone(3)
        self.refresh_zone(5)
        self.refresh_zone(7)

    def wait_lock(self, period, max):
        # wait for max number of periods (in seconds)
        count = 0
        while self.lock and count < max:
            time.sleep(period)

    def refresh_zone(self, zone_idx):
        # ONLY THIS METHOD SHOULD BE USED TO PRINT AN IMAGE TO THE DISPLAY

        # Wait if a lock is present (to avoid multiple async refreshes accessing the SPI simultaneously
        # If the LCD clears out during certain events, might need to increase the max wait
        self.wait_lock(0.005, 10)
        self.lock = True

        # Determine the start y position by adding the height of all previous zones
        self.disp.image(self.images[zone_idx], 270 if self.flip else 90, x=self.zone_y[zone_idx], y=0)

        # unlock so the next refresh can happen
        self.lock = False

    def splash_show(self):
        return
        self.clear()
        self.draw.text((0, self.top + 30), "pi Stomp!", font=self.splash_font, fill=(255, 255, 255))
        self.refresh()

    def cleanup(self):
        self.clear()

    def clear(self):
        self.disp.fill(0)