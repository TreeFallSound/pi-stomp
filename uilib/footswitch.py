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

from uilib.widget import *

class FootswitchWidget(Widget):

    def __init__(self, box, font, label, color, is_bypassed, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(FootswitchWidget,self).__init__(box, **kwargs)
        self.font = font
        self.label = label
        self.color = color
        self.is_bypassed = is_bypassed
        self.draw = None
        self.footswitch_ring_width = 7
        self.background = (0, 0, 0)  # TODO get palette from parent?
        self.foreground = (255, 255, 255)
        self.color_plugin_bypassed = (80, 80, 80)

    def _draw(self, image, draw, real_box):
        self.xy1 = (real_box.x0, real_box.y0)
        self.xy2 = (real_box.x0 + 60, real_box.y0 + 40)  # TODO should these offsets be here?
        self.draw = draw

        # halo
        self._draw_halo()

        # cap bottom
        fx1 = self.xy1[0] + 10
        fy1 = self.xy2[1] - 34
        fx2 = self.xy2[0] - 10
        fy2 = fy1 + 16
        draw.ellipse(((fx1, fy1), (fx2, fy2)), fill=self.background, outline="gray", width=2)

        # cap top
        fy1 -= 6
        fy2 -= 6
        draw.ellipse(((fx1, fy1), (fx2, fy2)), fill=self.background, outline="gray", width=2)

        # label
        draw.text((self.xy1[0], self.xy2[1]), self.label, self.foreground, self.font)

    def _draw_halo(self):
        hx1 = self.xy1[0] + 2
        hy1 = self.xy1[1] + 10
        hx2 = self.xy2[0] - 2
        hy2 = self.xy2[1] - 2
        color = self.color_plugin_bypassed if self.is_bypassed else self.color
        self.draw.ellipse(((hx1, hy1), (hx2, hy2)), fill=None, outline=color, width=self.footswitch_ring_width)

    def toggle(self, is_bypassed):
        self.is_bypassed = is_bypassed
        self._draw_halo()



