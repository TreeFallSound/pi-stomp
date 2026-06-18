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

from uilib.glyphs import ExpressionPedalGlyph, KnobGlyph
from uilib.text import *


#
# This is a class for drawing simple icon widgets using shapes (eg. ellipse, rect, line, etc.)
# with a text label
#


class Icon(TextWidget):
    """A simple icon with a text string.

    The icon graphic is a cached `Glyph` (`KnobGlyph` or `ExpressionPedalGlyph`)
    rendered into an RGBA surface and blitted at the left of the widget. Color
    is baked into the glyph at `add_knob()`/`add_pedal()` time (the widget's
    `fgnd_color` at that moment). Text is drawn to the right of the icon.
    """

    def __init__(self, box, text="", text_color=None, height=13, outline_width=2, **kwargs):
        self.height = height
        self.outline_width = outline_width
        self._glyph = None  # set by add_knob/add_pedal
        self.progress = None  # Progress value 0.0-1.0 for progress bar fill

        super(Icon, self).__init__(box, text=text, **kwargs)

        self.text_color = text_color if text_color is not None else self.fgnd_color

    def add_knob(self):
        self._glyph = KnobGlyph(self.height)

    def add_pedal(self):
        self._glyph = ExpressionPedalGlyph(self.height)

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

        # Blit the cached glyph alpha-mask (knob or expression pedal) at the
        # left, vertically centered in the widget, tinted to the icon colour.
        if self._glyph is not None:
            mask = self._glyph.render()
            ox, oy = ctx._f().topleft
            # Vertically center the square glyph in the widget height.
            gy = loc[1] + (ctx.height - mask.get_height()) // 2
            # Tint the white mask into the fgnd colour: blit a solid colour
            # fill onto a copy of the mask using BLEND_RGBA_MULT, then blit
            # the tinted copy onto the target. A plain MULT against the mask
            # in-place would corrupt the cached surface.
            tinted = mask.copy()
            color_surf = pygame.Surface(mask.get_size(), pygame.SRCALPHA)
            color_surf.fill(self.fgnd_color)
            tinted.blit(color_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            ctx.surface.blit(tinted, (loc[0] + ox, gy + oy))

        text_x = loc[0] + self.height + h_margin
        text_y = loc[1]

        if self.progress is None or self.progress <= 0:
            ctx.draw_text((text_x, text_y), self.text, fill=self.text_color, font=self.font)
            return

        # Progress bar: fill behind text, then draw text in two clipped passes
        # so the filled region gets inverted text and the unfilled region gets normal text.
        bar_width = ctx.width - self.height - (h_margin * 4)
        bar_height = ctx.height - (h_margin * 4)
        fill_width = int(bar_width * self.progress)
        if fill_width > 0:
            fill_box = Box(self.height + h_margin, 0, self.height + h_margin + fill_width, bar_height)
            ctx.draw_rectangle(fill_box, fill=self.text_color)

            ox, oy = ctx._f().topleft
            fill_x1_abs = ox + self.height + h_margin + fill_width
            cur_clip = ctx.surface.get_clip()

            # text over unfilled region
            r = pygame.Rect(fill_x1_abs, cur_clip.y, cur_clip.right - fill_x1_abs, cur_clip.height)
            ctx.surface.set_clip(cur_clip.clip(r))
            ctx.draw_text((text_x, text_y), self.text, fill=self.text_color, font=self.font)

            # text over filled region (inverted)
            r = pygame.Rect(cur_clip.x, cur_clip.y, fill_x1_abs - cur_clip.x, cur_clip.height)
            ctx.surface.set_clip(cur_clip.clip(r))
            ctx.draw_text((text_x, text_y), self.text, fill=self.bkgnd_color, font=self.font)

            ctx.surface.set_clip(cur_clip)
        else:
            ctx.draw_text((text_x, text_y), self.text, fill=self.text_color, font=self.font)
