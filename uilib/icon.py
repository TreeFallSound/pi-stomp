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

from uilib.text import *


#
# This is a class for drawing simple icon widgets using shapes (eg. ellipse, rect, line, etc.)
# with a text label
#


class Icon(TextWidget):
    """A simple icon with a text string"""

    def __init__(self, box, text="", text_color=None, height=13, outline_width=2, **kwargs):
        self.height = height
        self.outline_width = outline_width
        self.lines = []
        self.ellipses = []
        self.progress = None  # Progress value 0.0-1.0 for progress bar fill

        super(Icon, self).__init__(box, text=text, **kwargs)

        self.text_color = text_color if text_color is not None else self.fgnd_color

    def add_knob(self):
        # Widget-relative coords from (0, 0).
        loc = (0, 2)
        e = {
            'box': Box(loc[0], loc[1], loc[0] + self.height, loc[1] + self.height),
            'fill': self.bkgnd_color,
            'outline': self.fgnd_color,
            'height': self.outline_width,
        }
        self.ellipses.append(e)

        pointer_fudge = 2  # trim the upper right of the pointer
        l = {
            "xy": (
                (loc[0] + self.height - pointer_fudge, loc[1] + pointer_fudge),
                (loc[0] + int(self.height / 2), loc[1] + int(self.height / 2)),
            ),
            "fill": self.fgnd_color,
            "height": self.outline_width,
        }
        self.lines.append(l)

    def add_pedal(self):
        loc = (0, -1)
        l = {
            "xy": ((loc[0], loc[1] + self.height), (loc[0] + self.height, loc[1] + int(self.height / 3))),
            "fill": self.fgnd_color,
            "height": self.outline_width,
        }
        self.lines.append(l)

        l = {
            "xy": ((loc[0], loc[1] + self.height), (loc[0] + self.height, loc[1] + self.height)),
            "fill": self.fgnd_color,
            "height": self.outline_width + 2,
        }
        self.lines.append(l)

    def set_progress(self, progress):
        """Set progress value (0.0-1.0) for progress bar fill effect"""
        self.progress = max(0.0, min(1.0, progress)) if progress is not None else None
        if self.visible and self.parent:
            self.refresh()

    def _draw(self, ctx):
        h_margin, v_margin = self._get_margins()
        extra = self.outline
        hroom = ctx.width - h_margin - extra
        vroom = ctx.height - v_margin - extra
        if hroom < 0 or vroom < 0:
            return

        h_margin = 1
        loc = (h_margin, v_margin)

        for e in self.ellipses:
            ctx.draw_ellipse(e['box'], fill=e['fill'], outline=e['outline'], width=e['height'])

        for l in self.lines:
            ctx.draw_line(l['xy'], fill=l['fill'], width=l['height'])

        text_x = loc[0] + self.height + h_margin
        text_y = loc[1]

        if self.progress is None or self.progress <= 0:
            ctx.draw_text((text_x, text_y), self.text, fill=self.text_color, font=self.font)
            return

        # Progress bar: fill behind text, then draw text on top
        bar_width = ctx.width - self.height - (h_margin * 4)
        bar_height = ctx.height - (h_margin * 4)
        fill_width = int(bar_width * self.progress)
        if fill_width > 0:
            fill_box = Box(self.height + h_margin, 0, self.height + h_margin + fill_width, bar_height)
            ctx.draw_rectangle(fill_box, fill=self.text_color)
            ctx.draw_text((text_x, text_y), self.text, fill=self.bkgnd_color, font=self.font)
        else:
            ctx.draw_text((text_x, text_y), self.text, fill=self.text_color, font=self.font)
