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

    # Visual constants (in pixels).
    CAP_INSET_X = 10        # horizontal inset of the cap ellipse from each side
    CAP_HEIGHT = 16         # height of each cap ellipse
    CAP_STACK_OFFSET = 6    # how much the top cap sits above the bottom cap
    CAP_BOTTOM_MARGIN = 18  # gap between bottom of cap and bottom of cap area
    HALO_INSET = 2          # halo inset from frame edges
    HALO_TOP = 10           # halo top relative to frame top

    def _draw(self, ctx):
        w, h = ctx.width, ctx.height

        self._draw_halo(ctx)

        # Cap is a stack of two ellipses near the top of the frame, leaving
        # room below for the label.
        cap_x0 = self.CAP_INSET_X
        cap_x1 = w - self.CAP_INSET_X
        cap_bottom_y = h - self.CAP_BOTTOM_MARGIN - self.CAP_HEIGHT
        cap_top_y = cap_bottom_y - self.CAP_STACK_OFFSET

        # cap bottom
        ctx.draw_ellipse(Box(cap_x0, cap_bottom_y, cap_x1, cap_bottom_y + self.CAP_HEIGHT),
                         fill=self.background, outline="gray", width=2)
        # cap top
        ctx.draw_ellipse(Box(cap_x0, cap_top_y, cap_x1, cap_top_y + self.CAP_HEIGHT),
                         fill=self.background, outline="gray", width=2)

        # label sits at the bottom of the frame
        ctx.draw_text((0, h), self.label, self.foreground, self.font)

    def _draw_halo(self, ctx):
        # When an unbound footswitch toggles active, self.color is None. PIL's
        # ImageDraw silently fell back to its default ink (white); pygame skips
        # the draw entirely. Fall back to foreground to preserve the look.
        color = self.color_plugin_bypassed if self.is_bypassed else (self.color or self.foreground)
        ctx.draw_ellipse(
            Box(self.HALO_INSET, self.HALO_TOP,
                ctx.width - self.HALO_INSET, ctx.height - self.HALO_INSET),
            fill=None, outline=color, width=self.footswitch_ring_width,
        )

    def toggle(self, is_bypassed):
        self.is_bypassed = is_bypassed
