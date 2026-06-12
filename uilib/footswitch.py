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

from uilib.config import Config
from uilib.widget import Widget


class FootswitchWidget(Widget):
    """Minimal footswitch indicator: a "keycap" outline hugging a centered label.

    The keycap is the accent color — top edge with rounded top corners and open
    sides, no bottom edge. Accent is the configured footswitch color when ON, or
    DIMMED_BG when OFF. Unbound slots show "A".."D" as a placeholder.
    """

    DIMMED_BG = (90, 90, 90)  # #5a5a5a
    DEFAULT_COLOR = (255, 255, 255)

    KEYCAP_RADIUS = 4      # top-corner radius
    KEYCAP_PAD_X = 7       # horizontal gap between label and keycap sides
    KEYCAP_PAD_TOP = 3     # gap between keycap top and label
    KEYCAP_PAD_BOTTOM = 3  # how far the open legs extend below the label

    def __init__(self, box, num, label, color, is_bypassed, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(FootswitchWidget, self).__init__(box, **kwargs)
        self.font = Config().get_font("footswitch")
        self.num = num
        self.label = label
        self.color = color
        self.is_bypassed = is_bypassed

    def _draw_erase(self, image, draw, box):
        pass  # shroud panel owns the background; erasing here would wipe it out

    def _draw(self, image, draw, real_box):
        x0, y0 = real_box.x0, real_box.y0
        w, h = real_box.width, real_box.height

        is_on = not self.is_bypassed
        accent = (self.color if self.color is not None else self.DEFAULT_COLOR) if is_on else self.DIMMED_BG

        assert self.font
        text = self.label if self.label else chr(ord("A") + self.num)
        bbox = self.font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        # Center the keycap+label block in the slot.
        kw = tw + 2 * self.KEYCAP_PAD_X
        kh = th + self.KEYCAP_PAD_TOP + self.KEYCAP_PAD_BOTTOM
        kx0 = x0 + (w - kw) // 2
        ky0 = y0 + (h - kh) // 2
        kx1 = kx0 + kw - 1
        ky1 = ky0 + kh - 1

        bg = (0, 0, 0, 255) if not is_on else None
        self._draw_keycap(draw, kx0, ky0, kx1, ky1, accent, bg)

        tx = kx0 + self.KEYCAP_PAD_X - bbox[0]
        ty = ky0 + self.KEYCAP_PAD_TOP - bbox[1]
        draw.text((tx, ty), text, fill=accent, font=self.font)

    def _draw_keycap(self, draw, x0, y0, x1, y1, color, fill=None):
        # Keycap outline: rounded top corners, vertical sides, open bottom.
        if fill is not None:
            draw.rectangle([x0, y0, x1, y1], fill=fill)
        r = self.KEYCAP_RADIUS
        draw.line([(x0 + r, y0), (x1 - r, y0)], fill=color, width=1)        # top
        draw.line([(x0, y0 + r), (x0, y1)], fill=color, width=1)           # left
        draw.line([(x1, y0 + r), (x1, y1)], fill=color, width=1)           # right
        draw.arc([x0, y0, x0 + 2 * r, y0 + 2 * r], 180, 270, fill=color, width=1)
        draw.arc([x1 - 2 * r, y0, x1, y0 + 2 * r], 270, 360, fill=color, width=1)

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
