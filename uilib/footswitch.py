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

import pygame

from uilib.box import Box
from uilib.config import Config
from uilib.glyphs import KeycapCornerGlyph
from uilib.misc import get_text_size
from uilib.widget import Widget


class FootswitchWidget(Widget):
    """Footswitch indicator: a keycap outline (rounded top, open bottom) centered in the slot.

    Accent color is ON when bound and active, dimmed otherwise.
    """

    UNBOUND_BG = (50, 50, 50)
    BOUND_OFF_BG = (90, 90, 90)
    DEFAULT_COLOR = (255, 255, 255)

    KEYCAP_RADIUS = 4
    KEYCAP_PAD_X = 7
    KEYCAP_PAD_TOP = 3
    KEYCAP_PAD_BOTTOM = 3
    KEYCAP_HEIGHT = 20

    def __init__(self, box, num, label, color, is_bypassed, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(FootswitchWidget, self).__init__(box, **kwargs)
        self.font = Config().get_font("footswitch")
        self.num = num
        self.label = label
        self.color = color
        self.is_bypassed = is_bypassed
        self._corner_cache: dict = {}

    def _fit(self, text, max_w):
        """Largest leading substring fitting max_w px."""
        if not text:
            return text
        tw, _ = get_text_size(text, self.font)
        if tw <= max_w:
            return text
        out = ""
        for ch in text:
            tw, _ = get_text_size(out + ch, self.font)
            if tw > max_w:
                break
            out += ch
        return out

    def _draw_erase(self, ctx):
        pass  # parent.refresh() clears the RGBA surface and re-applies shroud before drawing us

    def _draw(self, ctx):
        w, h = ctx.width, ctx.height
        is_on = not self.is_bypassed

        if is_on:
            accent = self.color if self.color is not None else self.DEFAULT_COLOR
        else:
            accent = self.BOUND_OFF_BG if self.color is not None else self.UNBOUND_BG

        text = self.label if self.label else chr(ord("A") + self.num)
        text = self._fit(text, w - 2 * self.KEYCAP_PAD_X)

        tw, _ = get_text_size(text, self.font)
        kw = tw + 2 * self.KEYCAP_PAD_X
        kh = self.KEYCAP_HEIGHT
        kx0 = (w - kw) // 2
        ky0 = (h - kh) // 2
        kx1 = kx0 + kw - 1
        ky1 = ky0 + kh - 1

        fill = None if is_on else (0, 0, 0)
        self._draw_keycap(ctx, kx0, ky0, kx1, ky1, accent, fill)

        tx = kx0 + self.KEYCAP_PAD_X
        ty = ky0 + self.KEYCAP_PAD_TOP
        ctx.draw_text((tx, ty), text, fill=accent, font=self.font)

    def _corner_surfs(self, r: int, color) -> tuple:
        """Cached (tl, tr) SRCALPHA surfaces for rounded corners.

        Returns an (r+1)x(r+1) surface with the top-left arc drawn on a
        transparent background (analytic AA via `KeycapCornerGlyph`),
        plus a horizontal flip for the top-right. Composites correctly
        on RGBA — the 1px stroke aligns with the keycap's straight edges.
        """
        if isinstance(color, pygame.Color):
            key = (color.r, color.g, color.b, color.a)
        elif isinstance(color, (list, tuple)):
            key = tuple(color) if len(color) == 4 else (color[0], color[1], color[2], 255)
        else:
            key = (255, 255, 255, 255)
        if key not in self._corner_cache:
            rgb = (key[0], key[1], key[2])
            tl = KeycapCornerGlyph(r, rgb).render()
            tr = pygame.transform.flip(tl, True, False)
            self._corner_cache[key] = (tl, tr)
        return self._corner_cache[key]

    def _draw_keycap(self, ctx, kx0, ky0, kx1, ky1, color, fill=None):
        """Keycap outline: rounded top corners, vertical sides, open bottom."""
        r = self.KEYCAP_RADIUS
        if fill is not None:
            ctx.draw_rectangle(Box(kx0, ky0, kx1 + 1, ky1 + 1), fill=fill)

        # Straight edges
        ctx.draw_line([(kx0 + r, ky0), (kx1 - r, ky0)], fill=color, width=1)  # top
        ctx.draw_line([(kx0, ky0 + r), (kx0, ky1)], fill=color, width=1)  # left
        ctx.draw_line([(kx1, ky0 + r), (kx1, ky1)], fill=color, width=1)  # right

        # AA corners: blit cached (r+1)x(r+1) surfaces rendered on transparent background
        tl, tr = self._corner_surfs(r, color)
        ox, oy = ctx._f().topleft
        ctx.surface.blit(tl, (kx0 + ox, ky0 + oy))
        ctx.surface.blit(tr, (kx1 - r + ox, ky0 + oy))

    def refresh(self, box=None):
        # Delegate to parent so the ShroudedPanel re-applies its shroud gradient
        # before drawing children — a widget-only refresh would leave the slot
        # area transparent (no shroud) where we cleared for the previous keycap.
        if self.parent is not None:
            self.parent.refresh()
        else:
            super().refresh(box)

    def set_selected(self, selected):
        parent = self.parent
        super().set_selected(selected)
        if parent is not None:
            parent.refresh()

    def toggle(self, is_bypassed):
        self.is_bypassed = is_bypassed
