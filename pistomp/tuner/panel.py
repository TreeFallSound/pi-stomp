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

import statistics
import time
from collections import deque
from pathlib import Path
from typing import Callable, Literal

from uilib.box import Box
from uilib.config import Config
from uilib.misc import get_text_bbox, get_text_size
from uilib.panel import Panel
from uilib.pygame_init import font as make_font
from uilib.label import Label
from uilib.text import Button
from uilib.widget import Widget

from pistomp.input.event import ControllerEvent
from pistomp.input.sink import InputSink

_FONTS_DIR = Path(__file__).resolve().parents[2] / "fonts"


from pistomp.tuner.engine import TunerEngine, TunerReading

_W = 320  # display width

# ── type aliases ─────────────────────────────────────────────────────────────

Color = tuple[int, int, int]
Zone = Literal["in_tune", "accent", "red"]

# ── zone colour thresholds ────────────────────────────────────────────────────

_IN_TUNE_THRESH: float = 2.0
_RED_THRESH: float = 20.0

_ZONE_COLORS: dict[Zone, Color] = {
    "in_tune": (0, 200, 0),
    "accent": (255, 180, 0),
    "red": (210, 40, 40),
}


def _zone(cents: float) -> Zone:
    if abs(cents) <= _IN_TUNE_THRESH:
        return "in_tune"
    if abs(cents) <= _RED_THRESH:
        return "accent"
    return "red"


def _zone_color(cents: float) -> Color:
    return _ZONE_COLORS[_zone(cents)]


# ── TunerHeaderWidget ────────────────────────────────────────────────────────


class TunerHeaderWidget(Widget):
    """Centered note name only. Cents and Hz have moved to the offset bar."""

    MUTED_COLOR: Color = (90, 90, 90)

    def __init__(self, box: Box, note_font, **kwargs) -> None:
        super().__init__(box=box, **kwargs)
        self._note_font = note_font

        nb = get_text_bbox("A4", note_font)
        # header-local y: box.y0 is 0 here, but keep the expression honest.
        note_y = (box.height - (nb[3] - nb[1])) // 2 - nb[1]
        self._note_label = Label(0, note_y, note_font, parent=self)

    # ── drawing ───────────────────────────────────────────────────────────────

    def _draw_erase(self, ctx) -> None:
        pass  # bg painted by Label._draw_erase only over its own bbox

    def _draw(self, ctx) -> None:
        pass  # Label child draws itself via do_draw recursion

    # ── tick ──────────────────────────────────────────────────────────────────

    def _centered_x(self, text: str) -> int:
        bb = get_text_bbox(text, self._note_font)
        return (_W - (bb[2] - bb[0])) // 2 - bb[0]

    def tick(self, reading: TunerReading | None) -> None:
        note = reading.note if reading else "--"
        color = self.fgnd_color if reading else self.MUTED_COLOR
        self._note_label.set_text(note, color, x=self._centered_x(note))


_BTN_GAP = 2
_BTN_H = 28
_BTN_Y = 240 - _BTN_H - _BTN_GAP  # 2 px below
_BTN_W = (_W - 4 * _BTN_GAP) // 3  # 104 px each, leaves 2 px between/outside
_BTN_MUTE_ACTIVE_COLOR: Color = (140, 50, 0)


# ── TunerOffsetBar ───────────────────────────────────────────────────────────


class TunerOffsetBar(Widget):
    """Full-width bar that fills from centre toward left (flat) or right (sharp).

    The fill is colour-banded — green near centre, amber in the middle zone,
    red toward the edges — at the same cent breakpoints as the strobe zones.
    Only the moving edge is refreshed each tick.
    """

    BG_COLOR: Color = (20, 20, 20)
    BAR_MAX_CENTS: float = 50.0

    _CX: int = _W // 2  # 160

    # Zone boundaries in pixels from centre — computed with the same sqrt mapping
    # as _cents_to_px so colours stay aligned with their cent thresholds.
    _GREEN_PX: int = round(_CX * (_IN_TUNE_THRESH / BAR_MAX_CENTS) ** 0.5)  # ~32 px
    _YELLOW_PX: int = round(_CX * (_RED_THRESH / BAR_MAX_CENTS) ** 0.5)  # ~101 px

    def __init__(self, box: Box, **kwargs) -> None:
        kwargs.setdefault("bkgnd_color", TunerOffsetBar.BG_COLOR)
        super().__init__(box=box, **kwargs)
        self._bar_px: int = 0  # signed; positive = right (sharp), negative = left (flat)

    # ── drawing ──────────────────────────────────────────────────────────────

    def _draw_erase(self, ctx) -> None:
        pass  # _draw handles its own background

    def _draw(self, ctx) -> None:
        # Frame-relative: the bar's box starts at x=0, so _CX (=_W//2) and the
        # pixel offsets below are already in ctx coordinates. The SDL clip set
        # by a partial refresh restricts what actually lands.
        ctx.draw_rectangle(ctx.bounds, fill=self.BG_COLOR)
        self._paint_fill(ctx, self._bar_px)

    def _paint_fill(self, ctx, bar_px: int) -> None:
        if bar_px == 0:
            return
        cx = self._CX
        abs_px = abs(bar_px)
        sign = 1 if bar_px > 0 else -1
        h = ctx.height
        w = ctx.width

        def seg(a: int, b: int, color: Color) -> None:
            a, b = min(a, abs_px), min(b, abs_px)
            if a >= b:
                return
            sx0 = (cx + a) if sign > 0 else (cx - b)
            sx1 = (cx + b) if sign > 0 else (cx - a)
            sx0 = max(sx0, 0)
            sx1 = min(sx1, w)
            if sx0 >= sx1:
                return
            ctx.draw_rectangle(Box(sx0, 0, sx1, h), fill=color)

        seg(0, self._GREEN_PX, _ZONE_COLORS["in_tune"])
        seg(self._GREEN_PX, self._YELLOW_PX, _ZONE_COLORS["accent"])
        seg(self._YELLOW_PX, cx, _ZONE_COLORS["red"])

    # ── tick ─────────────────────────────────────────────────────────────────

    def _cents_to_px(self, cents: float) -> int:
        abs_px = int(self._CX * (min(abs(cents), self.BAR_MAX_CENTS) / self.BAR_MAX_CENTS) ** 0.5)
        return abs_px if cents >= 0.0 else -abs_px

    def tick(self, cents: float | None) -> None:
        new_px = self._cents_to_px(cents) if cents is not None else 0
        old_px = self._bar_px
        if new_px == old_px:
            return
        self._bar_px = new_px

        bx = self.box
        if bx is None:
            return

        # Direction change (or crossing zero): full redraw
        same_dir = old_px == 0 or new_px == 0 or (old_px > 0) == (new_px > 0)
        if not same_dir:
            self.refresh()
            return

        # Same direction: surgical refresh of only the delta column range
        cx = self._CX
        abs_old = abs(old_px)
        abs_new = abs(new_px)
        active = new_px if new_px != 0 else old_px
        sign = 1 if active > 0 else -1
        lo = min(abs_old, abs_new)
        hi = max(abs_old, abs_new)
        x0 = (cx + lo) if sign > 0 else (cx - hi)
        x1 = (cx + hi) if sign > 0 else (cx - lo)
        self.refresh(Box(x0, bx.y0, x1, bx.y1))


# ── StrobeWidget ─────────────────────────────────────────────────────────────


class StrobeWidget(Widget):
    """Sparse strobe: 6 accent stripes scrolling horizontally.

    Only trailing and leading edge columns are written to the LCD each tick;
    background pixels are never touched after initial setup.
    """

    STRIPE_W = 4
    STRIPE_P = 53
    N_STRIPES = 6
    BG_COLOR: Color = (20, 20, 20)
    RULE_COLOR: Color = (80, 80, 80)
    VELOCITY_SCALE = 10.0

    def __init__(self, box: Box, **kwargs) -> None:
        kwargs.setdefault("bkgnd_color", StrobeWidget.BG_COLOR)
        super().__init__(box=box, **kwargs)
        self._phase: float = 0.0
        self._zone: Zone = "accent"
        self._stripe_color: Color = _ZONE_COLORS["accent"]
        self._last_tick = time.monotonic()
        self._has_reading = False

    # ── drawing ──────────────────────────────────────────────────────────────

    def _draw_erase(self, ctx) -> None:
        pass  # handled inside _draw

    def _draw(self, ctx) -> None:
        # Frame-relative: the strobe box starts at x=0, so stripe phase (0.._W)
        # maps straight to ctx coordinates. Partial refreshes set the SDL clip,
        # so we always paint the full state and let the clip trim it.
        ctx.draw_rectangle(ctx.bounds, fill=self.BG_COLOR)
        w = ctx.width
        h = ctx.height

        if self._has_reading:
            y0 = 1
            y1 = h - 2
            if y0 <= y1:
                for i in range(self.N_STRIPES):
                    sx = (int(self._phase) + i * self.STRIPE_P) % _W
                    self._paint_overlap(ctx, sx, self.STRIPE_W, w, y0, y1)

        rx1 = max(0, w - 1)
        ctx.draw_line([(0, 0), (rx1, 0)], fill=self.RULE_COLOR)
        ctx.draw_line([(0, h - 1), (rx1, h - 1)], fill=self.RULE_COLOR)

    def _paint_overlap(self, ctx, sx: int, sw: int, w: int, y0: int, y1: int) -> None:
        """Paint the part of stripe [sx, sx+sw) (wrapping at _W) within [0, w)."""
        x0 = max(sx, 0)
        x1 = min(sx + sw, w)
        if x0 < x1:
            ctx.draw_rectangle(Box(x0, y0, x1, y1 + 1), fill=self._stripe_color)
        if sx + sw > _W:
            wrap_end = sx + sw - _W
            wx1 = min(wrap_end, w)
            if 0 < wx1:
                ctx.draw_rectangle(Box(0, y0, wx1, y1 + 1), fill=self._stripe_color)

    # ── batched partial-column refresh ─────────────────────────────────────────

    # Bridge gaps up to a stripe width when coalescing so a stripe's tail+lead
    # edges (and overlapping old/new positions) collapse to one transaction,
    # while the 53 px-spaced stripes stay separate.
    _MERGE_GAP = STRIPE_W

    def _flush_spans(self, spans: list[tuple[int, int]]) -> None:
        """Coalesce (x, w) column spans (wrapping at _W) into the minimal set of
        boxes and push one LCD transaction each. Per-tick overhead — set_window,
        tobytes/frombytes, rotate — dominates at 80 MHz SPI, so fewer, slightly
        wider transactions beat many thin ones."""
        bx = self.box
        if bx is None:
            return

        runs: list[tuple[int, int]] = []
        for x, w in spans:
            if w <= 0:
                continue
            x %= _W
            end = x + w
            if end <= _W:
                runs.append((x, end))
            else:
                runs.append((x, _W))
                runs.append((0, end - _W))
        if not runs:
            return

        runs.sort()
        cs, ce = runs[0]
        for s, e in runs[1:]:
            if s <= ce + self._MERGE_GAP:
                ce = max(ce, e)
            else:
                self.refresh(Box(cs, bx.y0, ce, bx.y1))
                cs, ce = s, e
        self.refresh(Box(cs, bx.y0, ce, bx.y1))

    def _stripe_spans_at(self, phase_int: int) -> list[tuple[int, int]]:
        return [((phase_int + i * self.STRIPE_P) % _W, self.STRIPE_W) for i in range(self.N_STRIPES)]

    # ── tick ─────────────────────────────────────────────────────────────────

    def tick(self, cents: float | None) -> None:
        now = time.monotonic()
        dt = min(now - self._last_tick, 0.5)
        self._last_tick = now

        if cents is None:
            if self._has_reading:
                self._has_reading = False
                self._zone = "accent"
                self._stripe_color = _ZONE_COLORS["accent"]
                self._flush_spans(self._stripe_spans_at(int(self._phase)))
            return

        if not self._has_reading:
            self._has_reading = True
            self._flush_spans(self._stripe_spans_at(int(self._phase)))
            return

        new_zone: Zone = _zone(cents)
        if new_zone != self._zone:
            self._zone = new_zone
            self._stripe_color = _zone_color(cents)
            self._flush_spans(self._stripe_spans_at(int(self._phase)))
            return

        K = (self.STRIPE_P / 50.0) * self.VELOCITY_SCALE
        velocity = max(-50.0, min(50.0, cents)) * K
        old_phase_int = int(self._phase)
        self._phase = (self._phase + velocity * dt) % float(_W)
        k = int(self._phase) - old_phase_int

        if k == 0:
            return

        if abs(k) >= self.STRIPE_W:
            # Old and new stripe positions don't overlap; coalescing still merges
            # any that landed within a stripe width of each other.
            self._flush_spans(self._stripe_spans_at(old_phase_int) + self._stripe_spans_at(int(self._phase)))
            return

        ak = abs(k)
        spans: list[tuple[int, int]] = []
        for i in range(self.N_STRIPES):
            old_sx = (old_phase_int + i * self.STRIPE_P) % _W
            if k > 0:
                tail_x = old_sx
                lead_x = (old_sx + self.STRIPE_W) % _W
            else:
                tail_x = (old_sx + self.STRIPE_W - ak) % _W
                lead_x = (old_sx - ak) % _W
            spans.append((tail_x, ak))
            spans.append((lead_x, ak))
        self._flush_spans(spans)


# ── TunerPanel ───────────────────────────────────────────────────────────────


class TunerPanel(Panel, InputSink):
    STALE_SECS = 4.0

    def __init__(
        self,
        engine: TunerEngine,
        on_dismiss: Callable[[], None],
        on_mute_toggle: Callable[[], None],
        on_input_toggle: Callable[[], None],
        muted: bool = False,
        input_port: int = 1,
    ) -> None:
        super().__init__(box=Box.xywh(0, 0, _W, 240), auto_destroy=True, no_dim=True)
        self._engine = engine

        note_font = make_font(str(_FONTS_DIR / "DejaVuSans-Bold.ttf"), 56)
        btn_font = Config().get_font("default")
        _, btn_text_h = get_text_size("Mute", btn_font)
        btn_v_margin = max(0, (_BTN_H - btn_text_h) // 2)

        self._header = TunerHeaderWidget(
            box=Box.xywh(0, 0, _W, 65),
            note_font=note_font,
            parent=self,
        )
        self._bar = TunerOffsetBar(box=Box.xywh(0, 65, _W, 13), parent=self)
        self._strobe = StrobeWidget(box=Box.xywh(0, 81, _W, _BTN_Y - _BTN_GAP - 81), parent=self)

        self._btn_close = Button(
            box=Box.xywh(_BTN_GAP, _BTN_Y, _BTN_W, _BTN_H),
            text="Close",
            font=btn_font,
            v_margin=btn_v_margin,
            outline_radius=4,
            parent=self,
            action=lambda *_: on_dismiss(),
        )
        self._btn_mute = Button(
            box=Box.xywh(_BTN_GAP * 2 + _BTN_W, _BTN_Y, _BTN_W, _BTN_H),
            text="Mute",
            font=btn_font,
            v_margin=btn_v_margin,
            outline_radius=4,
            parent=self,
            action=lambda *_: on_mute_toggle(),
        )
        self._btn_input = Button(
            box=Box.xywh(_BTN_GAP * 3 + _BTN_W * 2, _BTN_Y, _BTN_W, _BTN_H),
            text=f"Input {input_port}",
            font=btn_font,
            v_margin=btn_v_margin,
            outline_radius=4,
            parent=self,
            action=lambda *_: on_input_toggle(),
        )
        self.add_sel_widget(self._btn_close)
        self.add_sel_widget(self._btn_mute)
        self.add_sel_widget(self._btn_input)
        self._apply_mute_style(muted)
        self._cents_history: deque[float] = deque(maxlen=3)

    def handle(self, event: ControllerEvent) -> bool:
        return False

    def set_engine(self, engine: TunerEngine) -> None:
        self._engine = engine

    def set_muted(self, muted: bool) -> None:
        self._apply_mute_style(muted)
        self._btn_mute.refresh()

    def set_input_port(self, port: int) -> None:
        self._btn_input.set_text(f"Input {port}")

    def _apply_mute_style(self, muted: bool) -> None:
        self._btn_mute.set_background(_BTN_MUTE_ACTIVE_COLOR if muted else (0, 0, 0))

    def tick(self) -> None:
        reading = self._engine.get_reading()
        if reading is not None and time.monotonic() - reading.ts > self.STALE_SECS:
            reading = None

        if reading is not None:
            self._cents_history.append(reading.cents)
            cents = statistics.median(self._cents_history)
        else:
            self._cents_history.clear()
            cents = None

        self._header.tick(reading)
        self._bar.tick(cents)
        self._strobe.tick(cents)
