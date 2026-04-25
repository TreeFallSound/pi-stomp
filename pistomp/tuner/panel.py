import time
from typing import Callable, Literal

from PIL import ImageFont

from uilib.box import Box
from uilib.misc import InputEvent
from uilib.panel import Panel
from uilib.label import Label
from uilib.widget import Widget

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
    "red":    (210, 40, 40),
}


def _zone(cents: float) -> Zone:
    if abs(cents) <= _IN_TUNE_THRESH:
        return "in_tune"
    if abs(cents) <= _RED_THRESH:
        return "accent"
    return "red"


def _zone_color(cents: float) -> Color:
    return _ZONE_COLORS[_zone(cents)]


# ── helpers ───────────────────────────────────────────────────────────────────


def _draw_tracked(draw, xy: tuple[int, int], text: str, font, fill: Color, tracking: int = 4) -> None:
    """Draw text with extra inter-character spacing (wide tracking)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        bbox = font.getbbox(ch)
        x += (bbox[2] - bbox[0]) + tracking


# ── TunerHeaderWidget ────────────────────────────────────────────────────────


class TunerHeaderWidget(Widget):
    """Note name (left); cents and Hz stacked right-aligned on the right."""

    HZ_COLOR: Color = (90, 90, 90)

    def __init__(self, box: Box, note_font, info_font, **kwargs) -> None:
        super().__init__(box=box, **kwargs)
        self._note_font = note_font
        self._info_font = info_font

        # Cache layout positions — font metrics don't change after construction.
        h = box.height
        nb = note_font.getbbox("A4")
        note_y = box.y0 + (h - (nb[3] - nb[1])) // 2 - nb[1]
        cb = info_font.getbbox("0.0")
        th = cb[3] - cb[1]
        cents_y = box.y0 + (h // 2 - th) // 2 + 4
        hz_y = box.y0 + h // 2 + (h // 2 - th) // 2 - 4
        self._right_x = box.x1 - 8

        bg = self.bkgnd_color
        self._note_label = Label(box.x0 + 8, note_y, note_font, bg)
        self._cents_label = Label(0, cents_y, info_font, bg)
        self._hz_label = Label(0, hz_y, info_font, bg)
        self._cents_color: Color = _ZONE_COLORS["accent"]

    # ── drawing ───────────────────────────────────────────────────────────────

    def _draw_erase(self, image, draw, box) -> None:
        pass  # panel bg drawn once at mount; we never clear the full header

    def _draw(self, image, draw, real_box) -> None:
        """Full redraw — only at panel mount. Re-renders labels at stored positions."""
        if self._note_label.text:
            self._note_label.render(draw, self.fgnd_color, self._note_label.text)
        if self._cents_label.text:
            tw = self._info_font.getbbox(self._cents_label.text)[2]
            self._cents_label.render(draw, self._cents_color, self._cents_label.text,
                                     x=self._right_x - tw)
        if self._hz_label.text:
            tw = self._info_font.getbbox(self._hz_label.text)[2]
            self._hz_label.render(draw, self.HZ_COLOR, self._hz_label.text,
                                  x=self._right_x - tw)

    # ── tick ──────────────────────────────────────────────────────────────────

    def tick(self, reading: TunerReading | None) -> None:
        note = reading.note if reading else None
        cents_val = round(reading.cents, 1) if reading else None
        hz_val = round(reading.freq_hz, 1) if reading else None

        self._note_label.update(self, self.fgnd_color, note)

        if cents_val is not None:
            arrow = "\u25b4" if cents_val >= 0 else "\u25be"
            cents_text = f"{abs(cents_val):.1f} {arrow}"
            color = _zone_color(cents_val)
            self._cents_color = color
            tw = self._info_font.getbbox(cents_text)[2]
            self._cents_label.update(self, color, cents_text, x=self._right_x - tw)
        else:
            self._cents_label.update(self, self.fgnd_color, None)

        if hz_val is not None:
            hz_text = f"{hz_val:.1f} hz"
            tw = self._info_font.getbbox(hz_text)[2]
            self._hz_label.update(self, self.HZ_COLOR, hz_text, x=self._right_x - tw)
        else:
            self._hz_label.update(self, self.HZ_COLOR, None)


# ── TunerHintWidget ──────────────────────────────────────────────────────────


class TunerHintWidget(Widget):
    """Small uppercase wide-tracked exit prompt below the strobe."""

    TEXT = "CLICK/TAP TO EXIT"
    COLOR: Color = (80, 80, 80)
    TRACKING = 3

    def __init__(self, box: Box, font, **kwargs) -> None:
        super().__init__(box=box, **kwargs)
        self._font = font

    def _draw(self, image, draw, real_box) -> None:
        total_w = sum(self._font.getbbox(ch)[2] + self.TRACKING for ch in self.TEXT)
        total_w = max(total_w - self.TRACKING, 0)
        h = real_box.y1 - real_box.y0
        ch_h = self._font.getbbox("A")[3]
        x = real_box.x0 + (real_box.x1 - real_box.x0 - total_w) // 2
        y = real_box.y0 + (h - ch_h) // 2 - 4
        _draw_tracked(draw, (x, y), self.TEXT, self._font, self.COLOR, self.TRACKING)


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


class TunerPanel(Panel):
    STALE_SECS = 4.0

    def __init__(self, engine: TunerEngine, on_dismiss: Callable[[], None]) -> None:
        super().__init__(box=Box.xywh(0, 0, _W, 240), auto_destroy=True)
        self._engine = engine
        self._on_dismiss = on_dismiss

        note_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 56)
        info_font = ImageFont.truetype("DejaVuSans.ttf", 20)
        hint_font = ImageFont.truetype("DejaVuSans.ttf", 11)

        self._header = TunerHeaderWidget(
            box=Box.xywh(0, 0, _W, 65),
            note_font=note_font,
            info_font=info_font,
            parent=self,
        )
        self._strobe = StrobeWidget(box=Box.xywh(0, 68, _W, 135), parent=self)
        self._hint = TunerHintWidget(
            box=Box.xywh(0, 210, _W, 30),
            font=hint_font,
            parent=self,
        )

    def input_event(self, event) -> bool:
        if event in (InputEvent.CLICK, InputEvent.LONG_CLICK):
            self._on_dismiss()
            return True
        return False

    def tick(self) -> None:
        reading = self._engine.get_reading()
        if reading is not None and time.monotonic() - reading.ts > self.STALE_SECS:
            reading = None
        self._header.tick(reading)
        self._strobe.tick(reading.cents if reading else None)
