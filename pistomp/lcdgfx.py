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

import common.token as Token
import common.util as util
import os
import pistomp.lcd as abstract_lcd

from typing import Any
import pygame
from pygame import Surface
from uilib.pygame_init import font as _make_font

from pistomp.footswitch import Footswitch  # TODO would like to avoid this module knowing such details


class Lcd(abstract_lcd.Lcd):
    __single = None

    def __init__(self, cwd, lcd=None, backlight=None, touch=None):
        if Lcd.__single:
            raise RuntimeError("Attempted to create multiple instances of singleton class Lcd", Lcd.__single)
        Lcd.__single = self

        self._lcd: Any = lcd
        self._backlight: Any = backlight
        self._touch: Any = touch

        if lcd is None:
            from gfxhat import touch, lcd, backlight  # type: ignore[import-untyped]

            self._lcd, self._backlight, self._touch = lcd, backlight, touch

        # Polling divisor for main loop (monochrome LCD is fast)
        self.poll_divisor = 3

        self.width, self.height = self._lcd.dimensions()
        self.height -= 1  # TODO figure out why this is needed
        self.num_leds = 6

        # Zone dimensions
        self.zone_height = {0: 12, 1: 8, 2: 2, 3: 13, 4: 2, 5: 13, 6: 2, 7: 12}

        self.footswitch_xy = {0: (0, 0), 1: (51, 0), 2: (101, 0)}

        # Menu (System menu, Parameter edit, etc.)
        self.menu_height = self.height - self.zone_height[0] + 1  # TODO figure out why +1
        self.menu_image_height = self.menu_height * 10  # 10 pages (~40 parameters) enough?
        self.menu_surface = Surface((self.width, self.menu_image_height), pygame.SRCALPHA)
        self.graph_width = 127
        self.menu_y0 = 40

        # Element dimensions
        self.plugin_height = 11
        self.plugin_width = 24
        self.plugin_width_medium = 30
        self.plugin_bypass_thickness = 2
        self.plugin_label_length = 7
        self.footswitch_width = 26

        self.zones = 8
        # Surfaces for each zone (monochrome, stored as alpha channel for pixel manipulation)
        self.surfaces = [
            Surface((self.width, self.zone_height[0]), pygame.SRCALPHA),  # Pedalboard / Preset Title bar
            Surface((self.width, self.zone_height[1]), pygame.SRCALPHA),  # Analog Controllers
            Surface((self.width, self.zone_height[2]), pygame.SRCALPHA),  # Plugin selection
            Surface((self.width, self.zone_height[3]), pygame.SRCALPHA),  # Plugins Row 1
            Surface((self.width, self.zone_height[4]), pygame.SRCALPHA),  # Plugin selection
            Surface((self.width, self.zone_height[5]), pygame.SRCALPHA),  # Plugins Row 2
            Surface((self.width, self.zone_height[6]), pygame.SRCALPHA),  # Plugin selection
            Surface((self.width, self.zone_height[7]), pygame.SRCALPHA),
        ]  # Footswitch Plugins

        # Load fonts from the bundled fonts dir (pygame._freetype for consistent rendering)
        # Use monochrome (antialiased=False) for crisp rendering on 1-bit LCD
        fonts_dir = os.path.join(cwd, "fonts")
        self.splash_font = _make_font(os.path.join(fonts_dir, "DejaVuSans-Bold.ttf"), 18)
        self.splash_font.antialiased = False
        self.title_font = _make_font(os.path.join(fonts_dir, "DejaVuSans-Bold.ttf"), 11)
        self.title_font.antialiased = False
        self.label_font = _make_font(os.path.join(fonts_dir, "DejaVuSans-Bold.ttf"), 10)
        self.label_font.antialiased = False
        self.small_bold_font = _make_font(os.path.join(fonts_dir, "DejaVuSansMono-Bold.ttf"), 8)
        self.small_bold_font.antialiased = False
        self.small_font = _make_font(os.path.join(fonts_dir, "EtBt6001-JO47.ttf"), 6)
        self.small_font.antialiased = False

        # Splash
        splash_text = Surface((103, 63), pygame.SRCALPHA)
        self.splash_font.render_to(splash_text, (7, 20), "pi Stomp!", (255, 255, 255))
        # Rotate and copy to main splash surface
        rotated = pygame.transform.rotate(splash_text, -24)
        self.splash = Surface((self.width, self.height), pygame.SRCALPHA)
        self.splash.blit(rotated, (0, 0))
        self.splash_show()

        # Turn on Backlight
        self.enable_backlight()

        self.supports_toolbar = False

        self.plugins = []  # drawn plugins, for bypass-indicator redraw on refresh_plugins

    def poll_updates(self):
        pass  # lcdgfx pushes eagerly on every refresh call

    def clear_select(self):
        pass

    def draw_tools(self, wifi_type, eq_type, bypass_type, system_type):
        pass

    def update_wifi(self, wifi_status):
        pass

    def update_bypass(self, bypass):
        pass

    def update_eq(self, eq_status):
        pass

    def draw_tool_select(self, tool_type):
        pass

    def splash_show(self, boot=True):
        for x in range(0, self.width):
            for y in range(0, self.height):
                pixel = self.splash.get_at((x, y))[0]  # Get alpha channel value
                self._lcd.set_pixel(self.width - x - 1, self.height - y, pixel)
        self._lcd.show()

    def _surface_get_pixel(self, surface: Surface, x: int, y: int) -> bool:
        """Get pixel value from surface (True = white/1, False = black/0)."""
        if x < 0 or x >= surface.get_width() or y < 0 or y >= surface.get_height():
            return False
        color = surface.get_at((x, y))
        # Check if pixel is white (lit) - use any of R, G, or B channel
        return color[0] > 127

    def erase_zone(self, zone_idx):
        self.surfaces[zone_idx].fill((0, 0, 0, 0))

    def refresh_zone(self, zone_idx):
        # Determine the start y position by adding the height of all previous zones
        y_offset = 0
        for i in range(zone_idx):
            y_offset += self.zone_height[i]

        # Set Pixels from surface
        for x in range(0, self.width):
            for y in range(0, self.zone_height[zone_idx]):
                pixel = self._surface_get_pixel(self.surfaces[zone_idx], x, y)
                self._lcd.set_pixel(self.width - x - 1, self.height - y - y_offset, pixel)
        self._lcd.show()

    def refresh_menu(self, highlight_range=None, scroll_offset=0):
        # Set Pixels
        y_offset = self.zone_height[0]
        for x in range(0, self.width):
            for y in range(0, self.menu_height):
                y_draw = y + scroll_offset
                if y_draw < self.menu_image_height:
                    pixel = self._surface_get_pixel(self.menu_surface, x, y_draw)
                    if highlight_range and (y_draw >= highlight_range[0]) and (y_draw <= highlight_range[1]):
                        pixel = not pixel
                    self._lcd.set_pixel(self.width - x - 1, self.height - y - y_offset, pixel)
        self._lcd.show()

    # Plugin panels (not supported on monochrome LCD)
    def show_plugin_panel(self, panel):
        pass

    def hide_plugin_panel(self):
        pass

    def has_active_fullscreen_panel(self):
        return False

    @property
    def plugin_panel(self):
        return None

    def refresh_plugins(self):
        for p in self.plugins:
            surf = self.surfaces[p.lcd_xyz[2]]
            color = (255, 255, 255, 255) if not p.is_bypassed() else (0, 0, 0, 0)
            pygame.draw.line(
                surf, color, p.bypass_indicator_xy[0], p.bypass_indicator_xy[1], self.plugin_bypass_thickness
            )
        self.refresh_zone(2)
        self.refresh_zone(4)
        self.refresh_zone(6)
        self.refresh_zone(7)
        self.refresh_zone(5)
        self.refresh_zone(3)

    def enable_backlight(self):
        for x in range(6):
            self._backlight.set_pixel(x, 50, 100, 100)
        self._backlight.show()

    def cleanup(self):
        self._backlight.set_all(0, 0, 0)
        self._backlight.show()
        self._lcd.clear()
        self._lcd.show()
        for i in range(0, self.num_leds):
            self._touch.set_led(i, 0)

    def clear(self):
        for x in range(6):
            self._backlight.set_pixel(x, 0, 0, 0)
            self._touch.set_led(x, 0)
        self._backlight.show()
        self._lcd.clear()
        self._lcd.show()

    def erase_all(self):
        for z in range(self.zones):
            self.erase_zone(z)
            self.refresh_zone(z)

    # Menu Screens (uses deep_edit image and draw objects)
    def menu_show(self, page_title, menu_items):
        # Title (plugin name)
        self.erase_zone(0)
        self.title_font.render_to(self.surfaces[0], (0, -2), page_title, (255, 255, 255, 255))
        self.refresh_zone(0)

        self.menu_surface.fill((0, 0, 0, 0))

        # Menu Items
        idx = 0
        x = 0
        y = 2
        menu_list = list(sorted(menu_items))
        for i in menu_list:
            if idx == 0:
                self.small_font.render_to(
                    self.menu_surface, (x, y), "%s" % menu_items[i][Token.NAME], (255, 255, 255, 255)
                )
                x = 8  # indent after first element (back button)
            else:
                self.small_font.render_to(
                    self.menu_surface, (x, y), "%s %s" % (i, menu_items[i][Token.NAME]), (255, 255, 255, 255)
                )
            y += 10
            idx += 1
        self.refresh_menu()  # TODO Change name

    def menu_highlight(self, index):
        scroll_idx = 0
        highlight = (index * 10, index * 10 + 8)  # TODO replace 10
        num_visible = 3  # TODO
        if index > num_visible:
            scroll_idx = index - num_visible
        self.refresh_menu(highlight, scroll_idx * 10)

    # Parameter Value Edit
    def draw_value_edit(self, plugin_name, parameter, value):
        # Title (parameter name)
        self.erase_zone(0)
        title = "%s-%s" % (plugin_name, parameter.name)
        self.title_font.render_to(self.surfaces[0], (0, -2), title, (255, 255, 255, 255))
        self.refresh_zone(0)

        # Graph
        self.draw_value_edit_graph(parameter, value)

    def draw_value_edit_graph(self, parameter, value):
        self.menu_surface.fill((0, 0, 0, 0))
        y0 = self.menu_y0
        y1 = y0 - 2
        yt = 16
        x = 0  # TODO offset messes scale
        xpitch = 4
        self.label_font.render_to(self.menu_surface, (0, yt), "%s" % util.format_float(value), (255, 255, 255, 255))

        val = util.renormalize(value, parameter.minimum, parameter.maximum, 0, self.graph_width)
        yref = y1
        while x < self.graph_width:  # TODO 127 minus x pitch
            pygame.draw.line(self.menu_surface, (255, 255, 255, 255), (x + 2, y0), (x + 2, yref))

            if (x < val) and (x % xpitch) == 0:
                pygame.draw.rect(self.menu_surface, (255, 255, 255, 255), (x, y1, 1, y0 - y1 + 1))
                y1 = y1 - 1

            x = x + xpitch
            yref = yref - 1

        self.small_font.render_to(
            self.menu_surface, (0, self.menu_y0 + 4), "%d" % parameter.minimum, (255, 255, 255, 255)
        )
        self.small_font.render_to(
            self.menu_surface,
            (self.graph_width - (len(str(parameter.maximum)) * 4), self.menu_y0 + 4),
            "%d" % parameter.maximum,
            (255, 255, 255, 255),
        )

        self.refresh_menu()

    # Zone 0 - Pedalboard and Preset
    def draw_title(self, pedalboard, preset, invert_pb, invert_pre, highlight_only=False):
        self.erase_zone(0)

        pb_bbox = self.title_font.get_rect(pedalboard)
        pb_size = pb_bbox.width
        font_height = pb_bbox.height
        y = 0  # baseline at top of zone

        # Pedalboard Name
        if invert_pb:
            pygame.draw.rect(self.surfaces[0], (255, 255, 255, 255), (1, y, pb_size, font_height - 2))
        fg = (0, 0, 0, 255) if invert_pb else (255, 255, 255, 255)
        self.title_font.render_to(self.surfaces[0], (1, y), pedalboard, fg)

        if preset is not None:
            # delimiter
            delimiter = "/"
            x = pb_size + 2
            self.title_font.render_to(self.surfaces[0], (x, y), delimiter, (255, 255, 255, 255))

            # Preset Name
            pre_bbox = self.title_font.get_rect(preset)
            pre_size = pre_bbox.width
            delim_bbox = self.title_font.get_rect(delimiter)
            x = x + delim_bbox.width
            x2 = x + pre_size
            y2 = font_height
            if invert_pre:
                pygame.draw.rect(self.surfaces[0], (255, 255, 255, 255), (x, y, x2 - x, y2 - 2))
            fg = (0, 0, 0, 255) if invert_pre else (255, 255, 255, 255)
            self.title_font.render_to(self.surfaces[0], (x, y), preset, fg)

        self.refresh_zone(0)

    # Zone 1 - Analog Assignments (Tweak, Expression Pedal, etc.)
    def draw_analog_assignments(self, controllers):
        zone = 1
        self.erase_zone(zone)

        exp = Token.NONE
        knob = Token.NONE
        for k, v in controllers.items():
            control_type = util.DICT_GET(v, Token.TYPE)
            if util.DICT_GET(v, Token.CATEGORY) == "External":
                port = util.DICT_GET(v, "port_name") or ""
                text = "%s:%s" % (self.shorten_name(port, self.plugin_width), util.DICT_GET(v, "midi_cc"))
            else:
                s = k.split(":")
                text = "%s:%s" % (
                    self.shorten_name(s[0], self.plugin_width),
                    self.shorten_name(s[1], self.plugin_width_medium),
                )
            if control_type == Token.EXPRESSION:
                exp = text
            elif control_type == Token.KNOB:
                knob = text

        surf = self.surfaces[zone]
        # Expression Pedal assignment
        pygame.draw.line(surf, (255, 255, 255, 255), (0, 5), (8, 1), 1)
        pygame.draw.line(surf, (255, 255, 255, 255), (0, 5), (8, 5), 2)
        self.small_font.render_to(surf, (10, 2), exp, (255, 255, 255, 255))

        # Tweak knob assignment (encoder dial)
        x = 66
        # PIL ellipse uses inclusive bounding box (x0,y0,x1,y1), pygame uses (x,y,w,h)
        # Original: ellipse(((x, 0), (x + 6, 6))) = 7x7 box
        pygame.draw.ellipse(surf, (255, 255, 255, 255), (x, 0, 7, 7))  # filled circle
        pygame.draw.line(surf, (0, 0, 0, 255), (x + 3, 0), (x + 3, 2), 1)  # knob pointer (black)
        self.small_font.render_to(surf, (x + 9, 2), knob, (255, 255, 255, 255))

        self.refresh_zone(zone)

    def draw_info_message(self, text):
        zone = 1
        self.erase_zone(zone)
        self.small_font.render_to(self.surfaces[zone], (0, 2), text, (255, 255, 255, 255))
        self.refresh_zone(zone)

    # Zones 2, 4, 6 - Plugin Selection
    def draw_plugin_select(self, plugin=None):
        # Clear all selection zones
        # TODO could be smarter about which zones to clear and refresh, but...
        self.erase_zone(2)
        self.erase_zone(4)
        self.erase_zone(6)

        if plugin is not None and plugin.lcd_xyz is not None:
            x = plugin.lcd_xyz[0]
            _y = plugin.lcd_xyz[1]
            zone = plugin.lcd_xyz[2] - 1

            surf = self.surfaces[zone]
            for dx in range(8, 17):
                surf.set_at((x + dx, 0), (255, 255, 255, 255))

        self.refresh_zone(2)
        self.refresh_zone(4)
        self.refresh_zone(6)

    # Zones 3, 5, 7 - Plugin Display
    def draw_box(self, xy, xy2, zone, text, round_bottom_corners=False):
        surf = self.surfaces[zone]
        # PIL rectangle uses inclusive coordinates, pygame uses (x,y,w,h)
        # For PIL (x0,y0,x1,y1) inclusive -> pygame (x0,y0,w,h) where w=x1-x0+1, h=y1-y0+1
        w = xy2[0] - xy[0] + 1
        h = xy2[1] - xy[1] + 1
        pygame.draw.rect(surf, (255, 255, 255, 255), (xy[0], xy[1], w, h), 1)
        # PIL point() in L-mode defaults to ink=0 (black), clearing the corner pixels
        surf.set_at(xy, (0, 0, 0, 255))  # top-left
        surf.set_at((xy2[0], xy[1]), (0, 0, 0, 255))  # top-right
        if round_bottom_corners:
            surf.set_at((xy[0], xy2[1]), (0, 0, 0, 255))  # bottom-left
            surf.set_at((xy2[0], xy2[1]), (0, 0, 0, 255))  # bottom-right
        self.small_font.render_to(surf, (xy[0] + 2, xy[1] + 2), text, (255, 255, 255, 255))

    def draw_plugin(self, zone, x, y, text, width, eol, plugin, round_bottom_corners=False):
        text = self.shorten_name(text, width)
        x2 = x + width
        if eol:
            x2 = x2 - 1

        plugin.lcd_xyz = (x, y, zone)
        self.draw_box((x, y), (x2, y + self.plugin_height), zone, text, round_bottom_corners)

        bypass_indicator_xy = ((x + 3, y + 9), (x2 - 3, y + 9))
        plugin.bypass_indicator_xy = bypass_indicator_xy
        color = (0, 0, 0, 255) if plugin.is_bypassed() else (255, 255, 255, 255)
        pygame.draw.line(
            self.surfaces[zone], color, bypass_indicator_xy[0], bypass_indicator_xy[1], self.plugin_bypass_thickness
        )

        if plugin not in self.plugins:
            self.plugins.append(plugin)

        return x2

    def draw_bound_plugins(self, plugins, footswitches):
        fss = footswitches.copy()
        for p in plugins:
            if p.has_footswitch is False:
                continue
            for c in p.controllers:
                if isinstance(c, Footswitch):
                    fs_id = c.id
                    assert c.parameter
                    fss[fs_id] = None
                    if c.parameter.symbol != ":bypass":  # TODO token
                        label = c.parameter.name
                    else:
                        label = p.instance_id[: self.plugin_label_length]
                        label = label.replace("_", "")
                    self.draw_plugin(
                        7,
                        self.footswitch_xy[fs_id][0],
                        self.footswitch_xy[fs_id][1],
                        label,
                        self.footswitch_width,
                        False,
                        p,
                        True,
                    )

        # Draw any footswitches which weren't found to be bound to a plugin
        for fs_id in range(len(fss)):
            if fss[fs_id] is None:
                continue
            label = "" if fss[fs_id].display_label is None else fss[fs_id].display_label
            xy2 = (
                self.footswitch_xy[fs_id][0] + self.footswitch_width,
                self.footswitch_xy[fs_id][1] + self.plugin_height,
            )
            self.draw_box((self.footswitch_xy[fs_id][0], self.footswitch_xy[fs_id][1]), xy2, 7, label, True)

        self.refresh_zone(7)

    def draw_plugins(self, plugins):
        self.plugins = []  # reset; draw_plugin repopulates (incl. via draw_bound_plugins)
        y = 0
        x = 0
        xwrap = 110  # scroll if exceeds this width
        _ymax = 64  # Maximum y for plugin LCD zone
        rect_x_pad = 2
        zone = 3
        self.erase_zone(3)
        self.erase_zone(5)

        count = 0
        for p in plugins:
            if not p.has_footswitch:
                count = count + 1
        width = self.plugin_width_medium if count <= 8 else self.plugin_width

        count = 0
        eol = False
        for p in plugins:
            if p.has_footswitch:
                continue
            label = p.instance_id[: self.plugin_label_length]
            label = label.replace("_", "")
            count += 1
            if count > 4:
                eol = True
                count = 0
            x = self.draw_plugin(zone, x, y, label, width, eol, p)
            eol = False
            x = x + rect_x_pad
            if x > xwrap:
                zone += 2
                x = 0
                if zone > 5:
                    break  # Only display 2 rows, huge pedalboards won't fully render
        self.refresh_plugins()

    def shorten_name(self, name, width):
        text = ""
        for x in name.lower().replace("_", "").replace("/", "").replace(" ", ""):
            test = text + x
            test_bbox = self.small_font.get_rect(test)
            test_size = test_bbox.width
            if test_size >= width:
                break
            text = test
        return text
