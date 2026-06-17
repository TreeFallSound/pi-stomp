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

from uilib.box import Box
from uilib.config import Config
from uilib.widget import Widget


class FootswitchWidget(Widget):

    # Visual constants, top-anchored so the label area lives inside the frame
    # (SDL clips to the widget frame; the old PIL renderer let text bleed past).
    CAP_INSET_X = 10
    CAP_HEIGHT = 16
    CAP_STACK_OFFSET = 6
    CAP_TOP_Y = 0           # top edge of upper cap
    CAP_BOTTOM_Y = 6        # top edge of lower cap (= CAP_TOP_Y + CAP_STACK_OFFSET)
    HALO_INSET_X = 2
    HALO_TOP = 10
    HALO_BOTTOM = 38        # bottom of halo, just under the lower cap
    LABEL_Y = 40            # baseline-area for the label, below the cap

    def __init__(self, box, num, label, color, is_bypassed, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(FootswitchWidget, self).__init__(box, **kwargs)
        self.font = Config().get_font("footswitch")
        self.num = num
        self.label = label
        self.color = color
        self.is_bypassed = is_bypassed
        self.footswitch_ring_width = 7
        self.background = (0, 0, 0)
        self.foreground = (255, 255, 255)
        self.color_plugin_bypassed = (80, 80, 80)

    def _draw(self, ctx):
        w = ctx.width

        self._draw_halo(ctx)

        cap_x0 = self.CAP_INSET_X
        cap_x1 = w - self.CAP_INSET_X

        # cap bottom
        ctx.draw_ellipse(Box(cap_x0, self.CAP_BOTTOM_Y, cap_x1, self.CAP_BOTTOM_Y + self.CAP_HEIGHT),
                         fill=self.background, outline="gray", width=2)
        # cap top
        ctx.draw_ellipse(Box(cap_x0, self.CAP_TOP_Y, cap_x1, self.CAP_TOP_Y + self.CAP_HEIGHT),
                         fill=self.background, outline="gray", width=2)

        # Label sits below the cap, inside the frame.
        ctx.draw_text((0, self.LABEL_Y), self.label, self.foreground, self.font)

    def _draw_halo(self, ctx):
        # When an unbound footswitch toggles active, self.color is None. PIL's
        # ImageDraw silently fell back to its default ink (white); pygame skips
        # the draw entirely. Fall back to foreground to preserve the look.
        color = self.color_plugin_bypassed if self.is_bypassed else (self.color or self.foreground)
        ctx.draw_ellipse(
            Box(self.HALO_INSET_X, self.HALO_TOP,
                ctx.width - self.HALO_INSET_X, self.HALO_BOTTOM),
            fill=None, outline=color, width=self.footswitch_ring_width,
        )

    def set_selected(self, selected):
        parent = self.parent
        super().set_selected(selected)
        # ShroudedPanel owns the background; incremental refresh leaves
        # selection artefacts because _draw_erase is a no-op.  Refresh
        # the whole panel so the shroud is re-applied cleanly.
        if parent is not None:
            parent.refresh()

    def toggle(self, is_bypassed):
        self.is_bypassed = is_bypassed
