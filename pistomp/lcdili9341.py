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
import os
import pistomp.lcdcolor as lcdcolor
import pistomp.tool as Tool
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
        self.small_font = ImageFont.truetype("DejaVuSans.ttf", 20)
        self.tiny_font = ImageFont.truetype("DejaVuSans.ttf", 16)
        #self.tiny_font = ImageFont.truetype(os.path.join(cwd, "fonts", "EtBt6001-JO47.ttf"), 12)

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

        # Zones
        self.ZONE_TOOLS = 0
        self.ZONE_TITLE = 1
        self.ZONE_ASSIGNMENTS = 2
        self.ZONE_PLUGINS1 = 3
        self.ZONE_PLUGINS2 = 4
        self.ZONE_PLUGINS3 = 5
        self.ZONE_FOOTSWITCHES = 6

        self.zones = 7
        self.zone_height = {0: 18,
                            1: 36,
                            2: 26,
                            3: 30,
                            4: 30,
                            5: 34,
                            6: 66}
        self.zone_y = {}
        self.flip = True  # Flip the LCD vertically
        self.calc_zone_y()

        # space between footswitch icons where index is the footswitch count
        #                        0    1    2    3    4    5
        self.footswitch_pitch = [120, 120, 120, 128, 86,  65]

        # Menu (System menu, Parameter edit, etc.)
        self.menu_height = self.height - self.zone_height[0] - self.zone_height[1]
        self.menu_image_height = self.menu_height * 10  # 10 pages (~80 parameters) enough?
        self.menu_image = Image.new('RGB', (self.width, self.menu_image_height))
        self.menu_draw = ImageDraw.Draw(self.menu_image)
        self.menu_highlight_box_height = 22 # fix for cutting off bottom of some letters
        self.menu_highlight_box = ()
        self.menu_y0 = 150
        self.graph_width = 300

        # Element dimensions
        self.plugin_height = 24
        self.plugin_width = 75
        self.plugin_width_medium = 75
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
                       Image.new('RGB', (self.width, self.zone_height[6]))] # Plugin selection
                       #Image.new('RGB', (self.width, self.zone_height[7]))]  # Footswitch Plugins

        self.draw = [ImageDraw.Draw(self.images[0]), ImageDraw.Draw(self.images[1]),
                     ImageDraw.Draw(self.images[2]), ImageDraw.Draw(self.images[3]),
                     ImageDraw.Draw(self.images[4]), ImageDraw.Draw(self.images[5]),
                     ImageDraw.Draw(self.images[6])]

        self.splash_image = Image.new('RGB', (self.width, 60))
        self.splash_draw = ImageDraw.Draw(self.splash_image)

        self.lock = False
        self.supports_toolbar = True
        self.check_vars_set()
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
        self.refresh_zone(self.ZONE_PLUGINS1)
        self.refresh_zone(self.ZONE_PLUGINS2)
        self.refresh_zone(self.ZONE_PLUGINS3)
        #self.refresh_zone(7)

    def wait_lock(self, period, max):
        # wait for max number of periods (in seconds)
        count = 0
        while self.lock and count < max:
            time.sleep(period)
            count += 1

    def render_image(self, image, y0, x0=0):
        # ONLY THIS METHOD SHOULD BE USED TO PRINT AN IMAGE TO THE DISPLAY
        # TODO check and possibly transform image to assure that it will fit the display without an error

        # Wait if a lock is present (to avoid multiple async refreshes accessing the SPI simultaneously
        # If the LCD clears out during certain events, might need to increase the max wait
        self.wait_lock(0.005, 10)
        self.lock = True

        # Since rotating 270 or 90, x becomes y, y becomes x
        self.disp.image(image, 270 if self.flip else 90, x=y0, y=x0)

        # unlock so the next refresh can happen
        self.lock = False

    def refresh_zone(self, zone_idx):
        self.render_image(self.images[zone_idx], self.zone_y[zone_idx])

    def refresh_menu(self, highlight_range=None, highlight_offset=0, scroll_offset=0):
        if highlight_range:
            highlight_width = 2
            x = 0
            y = 0
            y_draw = y + highlight_offset
            if y_draw < self.menu_image_height:
                xy = (x, y_draw)
                xy2 = (x + self.width, y_draw + self.menu_highlight_box_height)
                if self.menu_highlight_box:
                    self.draw_just_a_box(self.menu_draw, self.menu_highlight_box[0], self.menu_highlight_box[1],
                                False, self.background, highlight_width)

                self.draw_just_a_box(self.menu_draw, xy, xy2, False, self.highlight, highlight_width)
                self.menu_highlight_box = (xy, xy2)

        # render_image is a windowed subset of menu_image which contains the full menu content which may be
        # too long to be displayed.  Use transform to "scroll" that window of content.
        render_image = self.menu_image.transform((self.width, self.menu_height), Image.EXTENT,
                                                 (0, scroll_offset, self.width, self.menu_height + scroll_offset))
        self.render_image(render_image, 0)

    # Menu Screens (uses deep_edit image and draw objects)
    def menu_show(self, page_title, menu_items):
        self.menu_image.paste(self.background, (0, 0, self.width, self.menu_image_height))

        # Title (plugin name)
        self.draw_title(page_title, "", False, False, False)
        self.draw_info_message("")

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
                self.menu_draw.text((x, y), "%s %s" % (i, menu_items[i][Token.NAME]), self.foreground,
                                    self.small_font)
            y += self.menu_highlight_box_height
            idx += 1
        self.refresh_menu()

    def menu_highlight(self, index):
        scroll_idx = 0
        highlight = ((index * 10, index * 10 + 8))
        num_visible = int(round(self.menu_height / self.menu_highlight_box_height)) - 1
        if index > num_visible:
            scroll_idx = index - num_visible
        self.refresh_menu(highlight, index * self.menu_highlight_box_height,
                          scroll_idx * self.menu_highlight_box_height)

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

    def draw_tools(self, wifi_type, eq_type, bypass_type, system_type):
        if not self.supports_toolbar:
            return
        self.erase_zone(self.ZONE_TOOLS)
        tools = []
        if self.tool_wifi is None:
            self.tool_wifi = Tool.Tool(wifi_type, 220, 1, os.path.join(self.imagedir, "wifi_gray.png"))
            tools.append(self.tool_wifi)
        if self.tool_eq is None:
            self.tool_eq = Tool.Tool(eq_type, 250, 1, os.path.join(self.imagedir, "eq_gray.png"))
            tools.append(self.tool_eq)
        if self.tool_bypass is None:
            self.tool_bypass = Tool.Tool(bypass_type, 275, 1, os.path.join(self.imagedir, "power_gray.png"))
            tools.append(self.tool_bypass)
        if self.tool_system is None:
            self.tool_system = Tool.Tool(system_type, 296, 1, os.path.join(self.imagedir, "wrench_silver.png"))
            tools.append(self.tool_system)
        if len(tools) > 0:
            self.tools = tools
        for t in self.tools:
            self.images[self.ZONE_TOOLS].paste(t.image, (t.x, t.y))
        self.refresh_zone(self.ZONE_TOOLS)

    def draw_tool_select(self, tool_type):
        if not self.supports_toolbar:
            return
        for t in self.tools:
            if t.tool_type == tool_type:
                xy0 = (t.x - 4, t.y - 1)
                xy1 = (t.x + 17, t.y + 16)
                width = 1
                self.draw_box_outline(xy0, xy1, self.ZONE_TOOLS, color=self.highlight, width=width)
                self.refresh_zone(self.ZONE_TOOLS)
                self.selected_box = (xy0, xy1, 1)
                break

    def splash_show(self, boot=True):
        self.clear()
        color = self.color_splash_up if boot is True else self.color_splash_down
        self.splash_draw.text((50, self.top), "pi Stomp!", font=self.splash_font, fill=color)
        self.render_image(self.splash_image, 90, 0)

    def cleanup(self):
        self.clear()

    def clear(self):
        self.disp.fill(0)

