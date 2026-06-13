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

    UNBOUND_BG = (50, 50, 50)
    BOUND_OFF_BG = (90, 90, 90)
    DEFAULT_COLOR = (255, 255, 255)

    KEYCAP_RADIUS = 4  # top-corner radius
    KEYCAP_PAD_X = 7  # horizontal gap between label and keycap sides
    KEYCAP_PAD_TOP = 3  # gap between keycap top and label
    KEYCAP_PAD_BOTTOM = 3  # how far the open legs extend below the label
    KEYCAP_HEIGHT = 20  # total outline height including the padding

    ERASE_PAD = 1  # px around the keycap to absorb anti-aliasing fringe

    def __init__(self, box, num, label, color, is_bypassed, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(FootswitchWidget, self).__init__(box, **kwargs)
        self.font = Config().get_font("footswitch")
        self.num = num
        self.label = label
        self.color = color
        self.is_bypassed = is_bypassed
        self._drawn = None  # last keycap rect, relative to slot origin
        self._cap_height = self.KEYCAP_HEIGHT - self.KEYCAP_PAD_TOP - self.KEYCAP_PAD_BOTTOM
        self._font_ascent = self.font.getmetrics()[0]

    def _draw_erase(self, image, draw, box):
        # Repaint black over the previously drawn keycap so a wider one is fully
        # cleared before a narrower one is drawn (single-widget refresh skips the
        # panel-wide erase). The keycap stays centered within its slot, so erasing
        # just its own footprint never touches a neighbouring switch.
        if self._drawn is None:
            return
        p = self.ERASE_PAD
        kx0, ky0, kx1, ky1 = self._drawn
        draw.rectangle(
            [box.x0 + kx0 - p, box.y0 + ky0 - p, box.x0 + kx1 + p, box.y0 + ky1 + p],
            fill=(0, 0, 0, 255),
        )

    def _fit(self, text, max_w):
        # Largest leading substring whose width fits max_w (hard cut, no ellipsis).
        if max_w <= 0 or self.font.getbbox(text)[2] <= max_w:
            return text
        out = ""
        for ch in text:
            if self.font.getbbox(out + ch)[2] > max_w:
                break
            out += ch
        return out

    def _draw(self, image, draw, real_box):
        x0, y0 = real_box.x0, real_box.y0
        w, h = real_box.width, real_box.height

        is_on = not self.is_bypassed
        if is_on:
            accent = self.color if self.color is not None else self.DEFAULT_COLOR
        else:
            # Bound-but-off is slightly brighter than an unbound slot.
            accent = self.BOUND_OFF_BG if self.color is not None else self.UNBOUND_BG

        assert self.font
        text = self.label if self.label else chr(ord("A") + self.num)
        # Cap the keycap to the slot: hard-cut the label so the padded keycap
        # never exceeds the slot width, just like plugin labels.
        text = self._fit(text, w - 2 * self.KEYCAP_PAD_X)
        bbox = self.font.getbbox(text)
        tw = bbox[2] - bbox[0]

        # Center the keycap+label block in the slot.
        kw = tw + 2 * self.KEYCAP_PAD_X
        kh = self._cap_height + self.KEYCAP_PAD_TOP + self.KEYCAP_PAD_BOTTOM
        kx0 = x0 + (w - kw) // 2
        ky0 = y0 + (h - kh) // 2
        kx1 = kx0 + kw - 1
        ky1 = ky0 + kh - 1

        bg = (0, 0, 0, 255) if not is_on else None
        self._draw_keycap(draw, kx0, ky0, kx1, ky1, accent, bg)

        # Remember the keycap footprint (slot-relative) so the next refresh can
        # erase it even if the new label is narrower.
        self._drawn = (kx0 - x0, ky0 - y0, kx1 - x0, ky1 - y0)

        tx = kx0 + self.KEYCAP_PAD_X - bbox[0]
        baseline_y = ky0 + self.KEYCAP_PAD_TOP + self._cap_height
        ty = baseline_y - self._font_ascent
        draw.text((tx, ty), text, fill=accent, font=self.font)

    def _draw_keycap(self, draw, x0, y0, x1, y1, color, fill=None):
        # Keycap outline: rounded top corners, vertical sides, open bottom.
        if fill is not None:
            draw.rectangle([x0, y0, x1, y1], fill=fill)
        r = self.KEYCAP_RADIUS
        draw.line([(x0 + r, y0), (x1 - r, y0)], fill=color, width=1)  # top
        draw.line([(x0, y0 + r), (x0, y1)], fill=color, width=1)  # left
        draw.line([(x1, y0 + r), (x1, y1)], fill=color, width=1)  # right
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
