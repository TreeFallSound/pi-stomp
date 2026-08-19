# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

import pygame

from common.loop_progress import LoopFill, LoopProgress
from uilib.box import Box
from uilib.config import Color, Config
from uilib.glyphs import CircleGlyph, RingGlyph
from uilib.glyphs.perimeter_progress import PerimeterProgressGlyph
from uilib.glyphs.tint import tint_mask
from uilib.misc import InputEvent, get_text_size
from uilib.paint import PaintContext
from uilib.panel import ShroudedPanel
from uilib.widget import Widget

if TYPE_CHECKING:
    import pygame._freetype


class TapTempoProtocol(Protocol):
    anchor: float

    def is_enabled(self) -> bool: ...
    def get_bpm(self) -> float: ...


# Layout constants (pixels). The strip is 36px tall.
DOT_RADIUS = 6
DOT_TOP = 4
DOT_DIAMETER = 2 * DOT_RADIUS
LABEL_TOP = DOT_TOP + DOT_DIAMETER + 1  # 17

# Letter badge: same size and y position as a bound dot.
BADGE_RADIUS = DOT_RADIUS
BADGE_DIAMETER = 2 * BADGE_RADIUS
BADGE_CENTER_Y = DOT_TOP + DOT_RADIUS

# Font threshold: below this slot width the label won't fit at 18pt, so
# drop to the small font.
SMALL_FONT_THRESHOLD = 60

# Title white — same (255,255,255) used for pedalboard/snapshot titles.
TITLE_WHITE: Color = (255, 255, 255)

# Loop progress border: inset 1px all round, same radius/weight as the tap
# border so the two views read as the same frame.
PROGRESS_INSET = 1
PROGRESS_RADIUS = 5
PROGRESS_THICKNESS = 2.0
PROGRESS_GAP = 3.0  # notch between bars, px of arclength
CHASE_SPAN = 0.18  # turns of perimeter the indeterminate head covers
PULSE_STEPS = 8  # brightness quantisation; each step past this is a slot repaint
# The unfilled track, as a fraction of the state colour.
TRACK_DIM = 0.28


class FootswitchWidget(Widget):
    """Footswitch indicator: a colored dot (the "LED") with a label below,
    or a letter badge when unassigned.  When the underlying footswitch is the
    tap-tempo switch and tap tempo is enabled, the widget switches to a
    dedicated tap view: an amber pulsing border, a "TAP" header, and the
    current BPM in larger digits."""

    # Bound switches: bright when active, dim ring when off.
    UNBOUND_OFF_BG: Color = (40, 40, 40)
    BOUND_OFF_BG: Color = (90, 90, 90)
    BOUND_OFF_LABEL: Color = (140, 140, 140)
    # Unassigned badges: deliberately dim so they don't compete with bound
    # indicators. On is a muted gray, off is near-black.
    BADGE_ON_FILL: Color = (130, 130, 130)
    BADGE_OFF_BORDER: Color = (50, 50, 50)
    DEFAULT_COLOR: Color = (255, 255, 255)

    TAP_COLOR: Color = (255, 180, 0)  # amber — beat on / header text
    TAP_DIM_COLOR: Color = (110, 78, 0)  # dim amber — beat off
    TAP_BPM_COLOR: Color = (255, 255, 255)  # BPM digits are always white

    # Vertical layout within the 36px strip (draw_text places the line-box top,
    # which sits ~2px above cap tops for DejaVu at these sizes).
    _TAP_Y_LABEL = 2  # "TAP" header (14pt Bold)
    _TAP_Y_BPM = 17  # BPM digits (16pt Bold)

    # Two-line state view, same rhythm as the tap view.
    _STATE_Y_NAME = 2
    _STATE_Y_STATE = 17

    font: pygame._freetype.Font
    small_font: pygame._freetype.Font | None
    label: str | None
    color: Color | None
    num: int | None
    is_bypassed: bool
    taptempo: TapTempoProtocol | None
    state_label: str | None
    progress_fn: Callable[[], LoopProgress | None] | None
    _pulse_on: bool
    _progress: LoopProgress | None

    def __init__(
        self,
        box: Box,
        label: str | None,
        color: Color | None,
        is_bypassed: bool,
        small_font: pygame._freetype.Font | None = None,
        taptempo: TapTempoProtocol | None = None,
        state_label: str | None = None,
        progress_fn: Callable[[], LoopProgress | None] | None = None,
        **kwargs,
    ):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(FootswitchWidget, self).__init__(box, **kwargs)
        self.font = Config().get_font("footswitch")  # pyright: ignore[reportAttributeAccessIssue]
        self.small_font = small_font
        self.label = label
        self.color = color
        self.num = None
        self.is_bypassed = is_bypassed
        self.taptempo = taptempo
        self.state_label = state_label
        self.progress_fn = progress_fn
        self._pulse_on = True
        self._progress = None
        self._progress_key: tuple[int, int, int, int] | None = None

    def _tap_active(self) -> bool:
        return self.taptempo is not None and self.taptempo.is_enabled()

    def _slot_font(self) -> "pygame._freetype.Font":
        """Pick the largest font that comfortably fits the slot width."""
        if self.box is not None and self.box.width < SMALL_FONT_THRESHOLD and self.small_font is not None:
            return self.small_font
        return self.font

    def _fit(self, text: str, max_w: int, font: "pygame._freetype.Font") -> str:
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

    def _draw_erase(self, ctx: PaintContext) -> None:
        pass  # parent.refresh() clears the RGBA surface and re-applies shroud before drawing us

    def _draw(self, ctx: PaintContext) -> None:
        if self._tap_active():
            self._draw_tap(ctx)
            return

        w, _h = ctx.width, ctx.height
        is_on = not self.is_bypassed
        has_label = bool(self.label)

        if self.state_label is not None:
            self._draw_state(ctx, w)
        elif has_label:
            self._draw_dot_and_label(ctx, w, is_on)
        else:
            self._draw_letter_badge(ctx, w, is_on)

    def _draw_tap(self, ctx: PaintContext) -> None:
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

    def _draw_state(self, ctx: PaintContext, w: int) -> None:
        """Two-line view for a switch whose plugin publishes a state: name on
        top, state below in the state's own color. No dot — the coloured state
        word is the indicator, and 36px holds two lines or a dot, not both."""
        self._draw_progress(ctx, w, ctx.height)
        font = self._slot_font()

        name = self._fit(self.label or "", w - 2, font)
        nw, _ = get_text_size(name, font)
        ctx.draw_text(((w - nw) // 2, self._STATE_Y_NAME), name, fill=self.BOUND_OFF_LABEL, font=font)

        state = self._fit(self.state_label or "", w - 2, font)
        sw, _ = get_text_size(state, font)
        fill = self.color if self.color is not None else self.BOUND_OFF_LABEL
        ctx.draw_text(((w - sw) // 2, self._STATE_Y_STATE), state, fill=fill, font=font)

    def _draw_dot_and_label(self, ctx: PaintContext, w: int, is_on: bool) -> None:
        """Small dot on top, label centered below."""
        cx = w // 2
        cy = DOT_TOP + DOT_RADIUS

        if is_on:
            dot_color = self.color if self.color is not None else self.DEFAULT_COLOR
            mask = CircleGlyph(DOT_RADIUS).render()
            tinted = tint_mask(mask, dot_color)
            ox, oy = ctx._f().topleft
            ctx.surface.blit(tinted, (cx - DOT_RADIUS + ox, cy - DOT_RADIUS + oy))
            label_color = TITLE_WHITE
        else:
            ring_color = self.BOUND_OFF_BG if self.color is not None else self.UNBOUND_OFF_BG
            ox, oy = ctx._f().topleft
            bg_r = DOT_RADIUS + 3
            ctx.surface.blit(tint_mask(CircleGlyph(bg_r).render(), (0, 0, 0)), (cx - bg_r + ox, cy - bg_r + oy))
            ring = RingGlyph(DOT_RADIUS)
            tinted = tint_mask(ring.render(), ring_color)
            ctx.surface.blit(tinted, (cx - ring.half_size + ox, cy - ring.half_size + oy))
            label_color = self.BOUND_OFF_LABEL if self.color is not None else self.UNBOUND_OFF_BG

        font = self._slot_font()
        text = self._fit(self.label or "", w - 2, font)
        tw, _ = get_text_size(text, font)
        tx = (w - tw) // 2
        ctx.draw_text((tx, LABEL_TOP), text, fill=label_color, font=font)

    def _draw_letter_badge(self, ctx: PaintContext, w: int, is_on: bool) -> None:
        cx = w // 2
        cy = BADGE_CENTER_Y
        ox, oy = ctx._f().topleft

        fill = self.BADGE_ON_FILL if is_on else (0, 0, 0)
        fill_r = BADGE_RADIUS if is_on else BADGE_RADIUS + 3
        ctx.surface.blit(tint_mask(CircleGlyph(fill_r).render(), fill), (cx - fill_r + ox, cy - fill_r + oy))

        if not is_on:
            ring = RingGlyph(BADGE_RADIUS)
            ctx.surface.blit(
                tint_mask(ring.render(), self.BADGE_OFF_BORDER), (cx - ring.half_size + ox, cy - ring.half_size + oy)
            )

    def refresh(self, box=None):
        if self.parent is not None:
            if hasattr(self.parent, "refresh_child"):
                # XXX: fast path for shrouded panel; kinda gross coupling
                self.parent.refresh_child(self)  # pyright: ignore[reportAttributeAccessIssue]
            else:
                self.parent.refresh()
        else:
            super().refresh(box)


    def _progress_glyph(self, w: int, h: int) -> PerimeterProgressGlyph:
        return PerimeterProgressGlyph(
            w - 2 * PROGRESS_INSET, h - 2 * PROGRESS_INSET, PROGRESS_RADIUS, PROGRESS_THICKNESS
        )

    def _draw_progress(self, ctx: PaintContext, w: int, h: int) -> None:
        """The loop's position around the slot's border: one arc per bar, the
        elapsed part in the state colour over a dim track of the same hue."""
        progress = self._progress
        if progress is None or w <= 2 * PROGRESS_RADIUS or h <= 2 * PROGRESS_RADIUS:
            return

        glyph = self._progress_glyph(w, h)
        ox, oy = ctx._f().topleft
        at = (PROGRESS_INSET + ox, PROGRESS_INSET + oy)
        r, g, b = progress.color
        # Only the lit part carries the beat envelope -- a track that breathed
        # with it would read as the whole slot flickering.
        lit: Color = (int(r * progress.pulse), int(g * progress.pulse), int(b * progress.pulse))
        dim: Color = (int(r * TRACK_DIM), int(g * TRACK_DIM), int(b * TRACK_DIM))

        if progress.mode is LoopFill.STATIC:
            ctx.surface.blit(tint_mask(glyph.render(0.0, 1.0, progress.segments, PROGRESS_GAP), dim), at)
            return

        if progress.mode is LoopFill.CHASE:
            head = glyph.render(progress.position, progress.position + CHASE_SPAN)
            ctx.surface.blit(tint_mask(head, lit), at)
            return

        ctx.surface.blit(tint_mask(glyph.render(0.0, 1.0, progress.segments, PROGRESS_GAP), dim), at)
        filled = glyph.render(0.0, progress.position, progress.segments, PROGRESS_GAP)
        ctx.surface.blit(tint_mask(filled, lit), at)

    def poll_progress(self) -> bool:
        """Re-read the loop position; True when the drawn result would differ.

        Quantised to whole perimeter pixels — the position advances
        continuously but the border can only move a pixel at a time, and each
        step costs a slot repaint."""
        if self.progress_fn is None:
            return False
        progress = self.progress_fn()
        if progress is None:
            changed = self._progress is not None
            self._progress, self._progress_key = None, None
            return changed

        box = self.box
        w = box.width if box is not None else 0
        h = box.height if box is not None else 0
        if w <= 2 * PROGRESS_RADIUS or h <= 2 * PROGRESS_RADIUS:
            return False
        steps = self._progress_glyph(w, h).perimeter
        key = (
            progress.mode.value,
            progress.segments,
            int(progress.position * steps),
            int(progress.pulse * PULSE_STEPS),
        )

        self._progress = progress
        if key == self._progress_key:
            return False
        self._progress_key = key
        return True

    def tick(self) -> None:
        """Blink the tap border at tempo, phase-locked to the last tap."""
        taptempo = self.taptempo
        if taptempo is None or not taptempo.is_enabled():
            if self.poll_progress():
                self.refresh()
            return
        bpm = taptempo.get_bpm()
        if not bpm:
            # No tempo yet — show steady amber
            if not self._pulse_on:
                self._pulse_on = True
                self.refresh()
            return
        period = 60.0 / bpm
        phase = (time.monotonic() - taptempo.anchor) % period
        on = phase < period / 4
        if on != self._pulse_on:
            self._pulse_on = on
            self.refresh()

    def toggle(self, is_bypassed: bool) -> None:
        self.is_bypassed = is_bypassed


class FootswitchBarPanel(ShroudedPanel):
    """The footswitch strip, selectable as one whole widget (never per-switch:
    the individual FootswitchWidget children are never added to any sel_list).

    CLICK and LONG_CLICK both delegate to ``on_press`` — this panel holds no
    opinion on what that opens."""

    def __init__(
        self,
        box: Box,
        on_press: Callable[[], None] | None = None,
        **kwargs,
    ):
        super(FootswitchBarPanel, self).__init__(box=box, **kwargs)
        self.on_press = on_press

    def sel_children(self):
        return [self]

    def input_event(self, event: InputEvent) -> bool:
        if event in (InputEvent.CLICK, InputEvent.LONG_CLICK) and self.on_press is not None:
            self.on_press()
            return True
        return False
