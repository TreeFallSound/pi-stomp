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
import common.token as Token
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
        self.splash_font = ImageFont.truetype('DejaVuSans.ttf', 48)
        self.small_font = ImageFont.truetype("DejaVuSans.ttf", 18)
        #self.small_font = ImageFont.truetype(os.path.join(cwd, "fonts", "EtBt6001-JO47.ttf"), 11)

        # Colors
        self.background = (0, 0, 0)
        self.foreground = (255, 255, 255)
        self.highlight = (255, 255, 0)
        self.color_plugin = (100, 100, 240)
        self.color_plugin_bypassed = (80, 80, 80)
        #self.color_splash = (210, 70, 255)
        self.color_splash_up = (70, 255, 70)
        self.color_splash_down = (255, 20, 20)

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
                            5: 72,
                            6: 0,
                            7: 66}
        self.zone_y = {}
        self.flip = True  # Flip the LCD vertically
        self.calc_zone_y()

        # space between footswitch icons where index is the footswitch count
        #                        0    1    2    3    4    5
        self.footswitch_pitch = [120, 120, 120, 128, 86,  65]

        # Menu (System menu, Parameter edit, etc.)
        self.menu_height = self.height - self.zone_height[0]
        self.menu_image_height = self.menu_height * 10  # 10 pages (~40 parameters) enough?
        #self.menu_image = Image.new('RGB', (self.width, self.menu_image_height))
        self.menu_image = Image.new('RGB', (self.width, self.menu_height))
        self.menu_draw = ImageDraw.Draw(self.menu_image)
        self.menu_highlight_box_height = 20
        self.menu_highlight_box = ()
        self.menu_y0 = 150
        self.graph_width = 300

        # Element dimensions
        self.plugin_height = 22
        self.plugin_width = 56
        self.plugin_width_medium = 70
        self.plugin_rect_x_pad = 5
        self.plugin_bypass_thickness = 2
        self.plugin_label_length = 7
        self.footswitch_width = 56
        self.footswitch_height = 44
        self.footswitch_ring_width = 7

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
        self.splash_show()

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
        #self.refresh_zone(7)

    def wait_lock(self, period, max):
        # wait for max number of periods (in seconds)
        count = 0
        while self.lock and count < max:
            time.sleep(period)
            count += 1

    def render_image(self, image, y0):
        # ONLY THIS METHOD SHOULD BE USED TO PRINT AN IMAGE TO THE DISPLAY

        # Wait if a lock is present (to avoid multiple async refreshes accessing the SPI simultaneously
        # If the LCD clears out during certain events, might need to increase the max wait
        self.wait_lock(0.005, 10)
        self.lock = True

        # Since rotating 270 or 90, x becomes y, y becomes x
        self.disp.image(image, 270 if self.flip else 90, x=y0, y=0)

        # unlock so the next refresh can happen
        self.lock = False

    def refresh_zone(self, zone_idx):
        self.render_image(self.images[zone_idx], self.zone_y[zone_idx])

    def refresh_menu(self, highlight_range=None, scroll_offset=0):
        if highlight_range:
            highlight_width = 2
            x = 0
            y = 0
            y_draw = y + scroll_offset
            if y_draw < self.menu_image_height:
                xy = (x, y_draw)
                xy2 = (x + self.width, y_draw + self.menu_highlight_box_height)
                if self.menu_highlight_box:
                    self.draw_just_a_box(self.menu_draw, self.menu_highlight_box[0], self.menu_highlight_box[1],
                                False, self.background, highlight_width)

                self.draw_just_a_box(self.menu_draw, xy, xy2, False, self.highlight, highlight_width)
                self.menu_highlight_box = (xy, xy2)

        self.render_image(self.menu_image, 0)

    # Menu Screens (uses deep_edit image and draw objects)
    def menu_show(self, page_title, menu_items):
        self.menu_image.paste(self.background, (0, 0, self.width, self.menu_image_height))

        # Title (plugin name)
        self.draw_title(page_title, "", False, False, False)

        # Menu Items
        idx = 0
        x = 0
        y = 0
        menu_list = list(sorted(menu_items))
        for i in menu_list:
            if idx is 0:
                self.menu_draw.text((x, y), "%s" % menu_items[i][Token.NAME], self.foreground, self.small_font)
                x = 8   # indent after first element (back button)
            else:
                self.menu_draw.text((x, y), "%s %s" % (i, menu_items[i][Token.NAME]), self.foreground, self.small_font)
            y += self.menu_highlight_box_height
            idx += 1
        self.refresh_menu()

    def menu_highlight(self, index):
        # TODO the highlight calculations here are pulled from lcdgfx.py but aren't currently used by refresh_menu()
        # re-enable something similar when a endless list of items is needed
        scroll_idx = 0
        highlight = ((index * 10, index * 10 + 8))
        num_visible = 0  # TODO was 3 for GFX
        if index > num_visible:
            scroll_idx = index - num_visible
        self.refresh_menu(highlight, scroll_idx * self.menu_highlight_box_height)

    def draw_footswitch(self, xy1, xy2, zone, text, color):
        # Many fudge factors here to make the footswitch icon smaller than the highlight bounding box
        # TODO These aren't scalable to other LCD's

        # halo
        hx1 = xy1[0] + 2
        hy1 = xy1[1] + 10
        hx2 = xy2[0] - 2
        hy2 = xy2[1] - 2
        self.draw[zone].ellipse(((hx1, hy1), (hx2, hy2)), fill=None, outline=color, width=self.footswitch_ring_width)

        # cap bottom
        fx1 = xy1[0] + 10
        fy1 = xy2[1] - 34
        fx2 = xy2[0] - 10
        fy2 = fy1 + 16
        self.draw[zone].ellipse(((fx1, fy1), (fx2, fy2)), fill=self.background, outline="gray", width=2)

        # cap top
        fy1 -= 6
        fy2 -= 6
        self.draw[zone].ellipse(((fx1, fy1), (fx2, fy2)), fill=self.background, outline="gray", width=2)

        # label
        self.draw[zone].text((xy1[0], xy2[1]), text, self.foreground, self.small_font)

    def splash_show(self, boot=True):
        zone = 5
        self.clear()
        self.erase_zone(zone)
        color = self.color_splash_up if boot is True else self.color_splash_down
        self.draw[zone].text((50, self.top), "pi Stomp!", font=self.splash_font, fill=color)
        self.refresh_zone(zone)

    def cleanup(self):
        self.clear()

    def clear(self):
        self.disp.fill(0)

