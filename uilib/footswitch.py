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

import time

import pygame

from uilib.box import Box
from uilib.config import Config
from uilib.glyphs import CircleGlyph
from uilib.misc import get_text_size
from uilib.widget import Widget

# Layout constants (pixels). The strip is 36px tall.
DOT_RADIUS = 6
DOT_TOP = 4
DOT_DIAMETER = 2 * DOT_RADIUS
LABEL_TOP = DOT_TOP + DOT_DIAMETER + 2  # 18

# Letter badge: bigger dot centered vertically with the letter inside.
BADGE_RADIUS = 10
BADGE_DIAMETER = 2 * BADGE_RADIUS
BADGE_CENTER_Y = 18  # vertically centers the 20px badge in the 36px strip

# Font threshold: below this slot width the label won't fit at 18pt, so
# drop to the small font.
SMALL_FONT_THRESHOLD = 60

# Title white — same (255,255,255) used for pedalboard/snapshot titles.
TITLE_WHITE = (255, 255, 255)
BADGE_LETTER_COLOR = (0, 0, 0)


def _tint_mask(mask: pygame.Surface, color: tuple[int, int, int]) -> pygame.Surface:
    """Tint a white alpha-mask glyph into `color` (BLEND_RGBA_MULT on a copy)."""
    tinted = mask.copy()
    color_surf = pygame.Surface(mask.get_size(), pygame.SRCALPHA)
    color_surf.fill(color)
    tinted.blit(color_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return tinted


class FootswitchWidget(Widget):
    """Footswitch indicator: a colored dot (the "LED") with a label below,
    or a letter badge when unassigned.  When the underlying footswitch is the
    tap-tempo switch and tap tempo is enabled, the widget switches to a
    dedicated tap view: an amber pulsing border, a "TAP" header, and the
    current BPM in larger digits."""

    # Bound switches: bright when active, dim ring when off.
    UNBOUND_OFF_BG = (40, 40, 40)
    BOUND_OFF_BG = (90, 90, 90)
    # Unassigned badges: deliberately dim so they don't compete with bound
    # indicators. On is a muted gray, off is near-black.
    BADGE_ON_FILL = (130, 130, 130)
    BADGE_OFF_FILL = (30, 30, 30)
    DEFAULT_COLOR = (255, 255, 255)

    TAP_COLOR = (255, 180, 0)  # amber — beat on / header text
    TAP_DIM_COLOR = (110, 78, 0)  # dim amber — beat off
    TAP_BPM_COLOR = (255, 255, 255)  # BPM digits are always white

    # Vertical layout within the 36px strip (draw_text places the line-box top,
    # which sits ~2px above cap tops for DejaVu at these sizes).
    _TAP_Y_LABEL = 2  # "TAP" header (14pt Bold)
    _TAP_Y_BPM = 17  # BPM digits (16pt Bold)

    def __init__(self, box, num, label, color, is_bypassed, small_font=None, taptempo=None, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(FootswitchWidget, self).__init__(box, **kwargs)
        self.font = Config().get_font("footswitch")
        self.small_font = small_font
        self.num = num
        self.label = label
        self.color = color
        self.is_bypassed = is_bypassed
        self.taptempo = taptempo
        self._pulse_on = True

    def _tap_active(self):
        return self.taptempo is not None and self.taptempo.is_enabled()

    def _slot_font(self):
        """Pick the largest font that comfortably fits the slot width."""
        if self.box is not None and self.box.width < SMALL_FONT_THRESHOLD and self.small_font is not None:
            return self.small_font
        return self.font

    def _fit(self, text, max_w, font):
        """Largest leading substring fitting max_w px."""
        if not text:
            return text
        tw, _ = get_text_size(text, font)
        if tw <= max_w:
            return text
        out = ""
        for ch in text:
            tw, _ = get_text_size(out + ch, font)
            if tw > max_w:
                break
            out += ch
        return out

    def _draw_erase(self, ctx):
        pass  # parent.refresh() clears the RGBA surface and re-applies shroud before drawing us

    def _draw(self, ctx):
        if self._tap_active():
            self._draw_tap(ctx)
            return

        w, _h = ctx.width, ctx.height
        is_on = not self.is_bypassed
        has_label = bool(self.label)

        if has_label:
            self._draw_dot_and_label(ctx, w, is_on)
        else:
            self._draw_letter_badge(ctx, w, is_on)

    def _draw_tap(self, ctx):
        w, h = ctx.width, ctx.height
        border_color = self.TAP_COLOR if self._pulse_on else self.TAP_DIM_COLOR

        ctx.draw_rectangle(Box.xywh(1, 0, w - 2, h), outline=border_color, width=2, radius=5)

        label_font = Config().get_font("footswitch_badge")
        bpm_font = Config().get_font("footswitch_tap_bpm")

        # "TAP" header centered, color tracks the pulse
        if label_font is not None:
            lw, _ = get_text_size("TAP", label_font)
            ctx.draw_text(((w - lw) // 2, self._TAP_Y_LABEL), "TAP", fill=border_color, font=label_font)

        # BPM digits centered, always white
        bpm = self.taptempo.get_bpm() if self.taptempo is not None else 0
        digits = str(round(bpm)) if bpm else "--"
        if bpm_font is not None:
            dw, _ = get_text_size(digits, bpm_font)
            ctx.draw_text(((w - dw) // 2, self._TAP_Y_BPM), digits, fill=self.TAP_BPM_COLOR, font=bpm_font)

    def _draw_dot_and_label(self, ctx, w, is_on):
        """Small dot on top, label centered below."""
        cx = w // 2
        cy = DOT_TOP + DOT_RADIUS

        if is_on:
            dot_color = self.color if self.color is not None else self.DEFAULT_COLOR
            mask = CircleGlyph(DOT_RADIUS).render()
            tinted = _tint_mask(mask, dot_color)
            ox, oy = ctx._f().topleft
            ctx.surface.blit(tinted, (cx - DOT_RADIUS + ox, cy - DOT_RADIUS + oy))
            label_color = TITLE_WHITE
        else:
            ring_color = self.BOUND_OFF_BG if self.color is not None else self.UNBOUND_OFF_BG
            dot_box = Box.xywh(cx - DOT_RADIUS, cy - DOT_RADIUS, DOT_DIAMETER, DOT_DIAMETER)
            ctx.draw_ellipse(dot_box, outline=ring_color, width=1)
            label_color = self.BOUND_OFF_BG if self.color is not None else self.UNBOUND_OFF_BG

        font = self._slot_font()
        text = self._fit(self.label, w - 2, font)
        tw, _ = get_text_size(text, font)
        tx = (w - tw) // 2
        ctx.draw_text((tx, LABEL_TOP), text, fill=label_color, font=font)

    def _draw_letter_badge(self, ctx, w, is_on):
        """Filled dot with the slot letter inside in bold black (on and off)."""
        fill = self.BADGE_ON_FILL if is_on else self.BADGE_OFF_FILL
        cx = w // 2
        cy = BADGE_CENTER_Y

        mask = CircleGlyph(BADGE_RADIUS).render()
        tinted = _tint_mask(mask, fill)
        ox, oy = ctx._f().topleft
        ctx.surface.blit(tinted, (cx - BADGE_RADIUS + ox, cy - BADGE_RADIUS + oy))

        # Bold letter, centered on the dot centre via ink-bbox centering
        # (origin=False → get_rect returns the ink bbox; render_to's pen is
        # the top-left of that bbox, matching the PillGlyph approach).
        letter = chr(ord("A") + self.num)
        font = Config().get_font("footswitch_badge")
        assert font is not None, "footswitch_badge font not registered"
        prev = font.origin
        font.origin = False
        try:
            rect = font.get_rect(letter)
            tx = cx - rect.width // 2
            ty = cy - rect.height // 2
            if letter == "D":
                tx += 1
            font.render_to(ctx.surface, (tx + ox, ty + oy), letter, fgcolor=BADGE_LETTER_COLOR)
        finally:
            font.origin = prev

    def refresh(self, box=None):
        if self.parent is not None:
            if hasattr(self.parent, "refresh_child"):
                # XXX: fast path for shrouded panel; kinda gross coupling
                self.parent.refresh_child(self)  # pyright: ignore[reportAttributeAccessIssue]
            else:
                self.parent.refresh()
        else:
            super().refresh(box)

    def tick(self):
        """Blink the tap border at tempo, phase-locked to the last tap."""
        if not self._tap_active():
            return
        bpm = self.taptempo.get_bpm() if self.taptempo is not None else 0
        if not bpm:
            # No tempo yet — show steady amber
            if not self._pulse_on:
                self._pulse_on = True
                self.refresh()
            return
        period = 60.0 / bpm
        phase = (time.monotonic() - self.taptempo.anchor) % period
        on = phase < period / 4
        if on != self._pulse_on:
            self._pulse_on = on
            self.refresh()

    def toggle(self, is_bypassed):
        self.is_bypassed = is_bypassed
