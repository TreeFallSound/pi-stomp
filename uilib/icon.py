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
    def __init__(self, box, text='', text_color=None, height=13, outline_width=2, **kwargs):

        self.height = height
        self.outline_width = outline_width
        self.lines = []
        self.ellipses = []

        super(Icon,self).__init__(box, text=text, **kwargs)

        self.text_color = text_color if text_color is not None else self.fgnd_color

    def add_knob(self):
        # Widget-relative coords from (0, 0).
        loc = (0, 2)
        e = {
            'box': Box(loc[0], loc[1], loc[0] + self.height, loc[1] + self.height),
            'fill': self.bkgnd_color,
            'outline': self.fgnd_color,
            'height' : self.outline_width
        }
        self.ellipses.append(e)

        pointer_fudge = 2  # trim the upper right of the pointer
        l = {
            'xy': ((loc[0] + self.height - pointer_fudge, loc[1] + pointer_fudge),
                   (loc[0] + int(self.height / 2), loc[1] + int(self.height / 2))),
            'fill': self.fgnd_color,
            'height' : self.outline_width
        }
        self.lines.append(l)

    def add_pedal(self):
        loc = (0, -1)
        l = {
            'xy': ((loc[0], loc[1] + self.height),
                   (loc[0] + self.height, loc[1] + int(self.height / 3))),
            'fill': self.fgnd_color,
            'height' : self.outline_width
        }
        self.lines.append(l)

        l = {
            'xy': ((loc[0], loc[1] + self.height),
                   (loc[0] + self.height, loc[1] + self.height)),
            'fill': self.fgnd_color,
            'height' : self.outline_width + 2
        }
        self.lines.append(l)


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

        ctx.draw_text((loc[0] + self.height + h_margin, loc[1]), self.text, fill=self.text_color, font=self.font)

