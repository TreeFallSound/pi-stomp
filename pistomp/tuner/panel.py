import statistics
import time
from collections import deque
from typing import Callable, Literal

from PIL import ImageFont

from uilib.box import Box
from uilib.config import Config
from uilib.misc import get_text_size
from uilib.panel import Panel
from uilib.label import Label
from uilib.text import Button
from uilib.widget import Widget

from pistomp.input.event import ControllerEvent
from pistomp.input.sink import InputSink
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

        nb = note_font.getbbox("A4")
        # header-local y: box.y0 is 0 here, but keep the expression honest.
        note_y = (box.height - (nb[3] - nb[1])) // 2 - nb[1]
        self._note_label = Label(0, note_y, note_font, parent=self)

    # ── drawing ───────────────────────────────────────────────────────────────

    def _draw_erase(self, image, draw, box) -> None:
        pass  # bg painted by Label._draw_erase only over its own bbox

    def _draw(self, image, draw, real_box) -> None:
        pass  # Label child draws itself via _do_draw recursion

    # ── tick ──────────────────────────────────────────────────────────────────

    def _centered_x(self, text: str) -> int:
        bb = self._note_font.getbbox(text)
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

    def _draw_erase(self, image, draw, box) -> None:
        pass  # _draw handles its own background

    def _draw(self, image, draw, real_box) -> None:
        draw.rectangle(real_box.PIL_rect, fill=self.BG_COLOR)
        self._paint_fill(draw, real_box, self._bar_px)

    def _paint_fill(self, draw, real_box, bar_px: int) -> None:
        if bar_px == 0:
            return
        cx = self._CX
        abs_px = abs(bar_px)
        sign = 1 if bar_px > 0 else -1
        ry0 = real_box.y0
        ry1 = real_box.y1 - 1
        rx0 = real_box.x0
        rx1 = real_box.x1

        def seg(a: int, b: int, color: Color) -> None:
            a, b = min(a, abs_px), min(b, abs_px)
            if a >= b:
                return
            sx0 = (cx + a) if sign > 0 else (cx - b)
            sx1 = (cx + b) if sign > 0 else (cx - a)
            sx0 = max(sx0, rx0)
            sx1 = min(sx1, rx1)
            if sx0 >= sx1:
                return
            draw.rectangle([sx0, ry0, sx1 - 1, ry1], fill=color)

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

    def _draw_erase(self, image, draw, box) -> None:
        pass  # handled inside _draw

    def _draw(self, image, draw, real_box) -> None:
        draw.rectangle(real_box.PIL_rect, fill=self.BG_COLOR)

        if self._has_reading:
            rx0, rx1 = real_box.x0, real_box.x1
            y0 = real_box.y0 + 1
            y1 = real_box.y1 - 2
            if y0 <= y1:
                for i in range(self.N_STRIPES):
                    sx = (int(self._phase) + i * self.STRIPE_P) % _W
                    self._paint_overlap(draw, sx, self.STRIPE_W, rx0, rx1, y0, y1)

        bx = self.box
        if bx is None:
            return
        rx0, rx1 = real_box.x0, max(real_box.x0, real_box.x1 - 1)
        if real_box.y0 <= bx.y0:
            draw.line([(rx0, bx.y0), (rx1, bx.y0)], fill=self.RULE_COLOR)
        if real_box.y1 >= bx.y1:
            draw.line([(rx0, bx.y1 - 1), (rx1, bx.y1 - 1)], fill=self.RULE_COLOR)

    def _paint_overlap(self, draw, sx: int, sw: int, rx0: int, rx1: int, y0: int, y1: int) -> None:
        """Paint the part of stripe [sx, sx+sw) (wrapping at _W) within [rx0, rx1)."""
        x0 = max(sx, rx0)
        x1 = min(sx + sw, rx1)
        if x0 < x1:
            draw.rectangle([x0, y0, x1 - 1, y1], fill=self._stripe_color)
        if sx + sw > _W:
            wrap_end = sx + sw - _W
            wx0 = max(0, rx0)
            wx1 = min(wrap_end, rx1)
            if wx0 < wx1:
                draw.rectangle([wx0, y0, wx1 - 1, y1], fill=self._stripe_color)

    # ── partial-column refresh ────────────────────────────────────────────────

    def _refresh_col(self, x: int, w: int) -> None:
        """Refresh a w-pixel-wide column at x (with wrap at _W), full widget height."""
        if w <= 0:
            return
        bx = self.box
        if bx is None:
            return
        if x + w <= _W:
            self.refresh(Box(x, bx.y0, x + w, bx.y1))
        else:
            right_w = _W - x
            if right_w > 0:
                self.refresh(Box(x, bx.y0, _W, bx.y1))
            wrap_w = w - right_w
            if wrap_w > 0:
                self.refresh(Box(0, bx.y0, wrap_w, bx.y1))

    def _refresh_stripes_at(self, phase_int: int) -> None:
        for i in range(self.N_STRIPES):
            sx = (phase_int + i * self.STRIPE_P) % _W
            self._refresh_col(sx, self.STRIPE_W)

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
                self._refresh_stripes_at(int(self._phase))
            return

        if not self._has_reading:
            self._has_reading = True
            self._refresh_stripes_at(int(self._phase))
            return

        new_zone: Zone = _zone(cents)
        if new_zone != self._zone:
            self._zone = new_zone
            self._stripe_color = _zone_color(cents)
            self._refresh_stripes_at(int(self._phase))
            return

        if self._zone == "in_tune":
            return  # frozen — zero SPI writes

        K = (self.STRIPE_P / 50.0) * self.VELOCITY_SCALE
        velocity = max(-50.0, min(50.0, cents)) * K
        old_phase_int = int(self._phase)
        self._phase = (self._phase + velocity * dt) % float(_W)
        k = int(self._phase) - old_phase_int

        if k == 0:
            return

        if abs(k) >= self.STRIPE_W:
            self._refresh_stripes_at(old_phase_int)
            self._refresh_stripes_at(int(self._phase))
            return

        ak = abs(k)
        for i in range(self.N_STRIPES):
            old_sx = (old_phase_int + i * self.STRIPE_P) % _W
            if k > 0:
                tail_x = old_sx
                lead_x = (old_sx + self.STRIPE_W) % _W
            else:
                tail_x = (old_sx + self.STRIPE_W - ak) % _W
                lead_x = (old_sx - ak) % _W
            self._refresh_col(tail_x, ak)
            self._refresh_col(lead_x, ak)


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
        super().__init__(box=Box.xywh(0, 0, _W, 240), auto_destroy=True)
        self._engine = engine

        note_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 56)
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
