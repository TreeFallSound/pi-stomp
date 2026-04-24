import logging
import time
from typing import Callable, Literal

from PIL import ImageFont

from uilib.box import Box
from uilib.misc import InputEvent
from uilib.panel import Panel
from uilib.widget import Widget

from pistomp.tuner.engine import TunerEngine, TunerReading

_W = 320  # display width

# ── type aliases ─────────────────────────────────────────────────────────────

Color = tuple[int, int, int]
Zone = Literal["in_tune", "accent", "red"]

# ── zone colour thresholds (shared by strobe and header) ─────────────────────

_IN_TUNE_THRESH: float = 2.0  # cents — green
_RED_THRESH: float = 20.0  # cents — red beyond this

_IN_TUNE_COLOR: Color = (0, 200, 0)
_ACCENT_COLOR: Color = (255, 180, 0)
_RED_COLOR: Color = (210, 40, 40)


def _zone_color(cents: float) -> Color:
    if abs(cents) <= _IN_TUNE_THRESH:
        return _IN_TUNE_COLOR
    if abs(cents) <= _RED_THRESH:
        return _ACCENT_COLOR
    return _RED_COLOR


def _cents_zone(cents: float) -> Zone:
    if abs(cents) <= _IN_TUNE_THRESH:
        return "in_tune"
    if abs(cents) <= _RED_THRESH:
        return "accent"
    return "red"


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
        self._note: str | None = None
        self._cents: float | None = None
        self._hz: float | None = None

    def _draw(self, image, draw, real_box) -> None:
        h = real_box.y1 - real_box.y0
        mid_y = real_box.y0 + h // 2

        # Note — vertically centred in the full box height
        if self._note:
            try:
                nb = self._note_font.getbbox(self._note)
                note_y = real_box.y0 + (h - (nb[3] - nb[1])) // 2 - nb[1]
            except Exception:
                note_y = real_box.y0 + 2
            draw.text(
                (real_box.x0 + 8, note_y),
                self._note,
                font=self._note_font,
                fill=self.fgnd_color,
            )

        # Cents — top half, right-aligned, triangle on right
        if self._cents is not None:
            arrow = "\u25b4" if self._cents >= 0 else "\u25be"
            cents_text = f"{abs(self._cents):.1f} {arrow}"
            try:
                cb = self._info_font.getbbox(cents_text)
                tw, th = cb[2], cb[3] - cb[1]
            except Exception:
                tw, th = 60, 16
            cents_y = real_box.y0 + (h // 2 - th) // 2 + 4
            draw.text(
                (real_box.x1 - tw - 8, cents_y),
                cents_text,
                font=self._info_font,
                fill=_zone_color(self._cents),
            )

        # Hz — bottom half, right-aligned, greyed
        if self._hz is not None:
            hz_text = f"{self._hz:.1f} hz"
            try:
                hb = self._info_font.getbbox(hz_text)
                tw, th = hb[2], hb[3] - hb[1]
            except Exception:
                tw, th = 60, 16
            hz_y = mid_y + (h // 2 - th) // 2 - 4
            draw.text(
                (real_box.x1 - tw - 8, hz_y),
                hz_text,
                font=self._info_font,
                fill=self.HZ_COLOR,
            )

    def tick(self, reading: TunerReading | None) -> None:
        note = reading.note if reading else None
        cents = reading.cents if reading else None
        hz = reading.freq_hz if reading else None
        if note == self._note and cents == self._cents and hz == self._hz:
            return
        self._note = note
        self._cents = cents
        self._hz = hz
        self.refresh()


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
        total_w = 0
        for ch in self.TEXT:
            try:
                _, _, cw, _ = self._font.getbbox(ch)
            except Exception:
                cw = 8
            total_w += cw + self.TRACKING
        total_w = max(total_w - self.TRACKING, 0)

        h = real_box.y1 - real_box.y0
        try:
            _, _, _, ch_h = self._font.getbbox("A")
        except Exception:
            ch_h = 10
        x = real_box.x0 + (real_box.x1 - real_box.x0 - total_w) // 2
        y = real_box.y0 + (h - ch_h) // 2 - 4
        _draw_tracked(draw, (x, y), self.TEXT, self._font, self.COLOR, self.TRACKING)


# ── StrobeWidget ─────────────────────────────────────────────────────────────


class StrobeWidget(Widget):
    """Sparse strobe: 6 accent stripes scrolling horizontally.

    Only trailing and leading edge columns are written to the LCD each tick;
    background pixels are never touched after initial setup.
    """

    STRIPE_W = 8
    STRIPE_P = 53
    N_STRIPES = 6
    BG_COLOR: Color = (20, 20, 20)
    RULE_COLOR: Color = (80, 80, 80)
    VELOCITY_SCALE = 5.0

    def __init__(self, box: Box, **kwargs) -> None:
        kwargs.setdefault("bkgnd_color", StrobeWidget.BG_COLOR)
        super().__init__(box=box, **kwargs)
        self._phase: float = 0.0
        self._zone: Zone = "accent"
        self._stripe_color: Color = _ACCENT_COLOR
        self._last_tick = time.monotonic()
        self._active = False

    # ── drawing ──────────────────────────────────────────────────────────────

    def _draw_erase(self, image, draw, box) -> None:
        pass  # We handle erasing inside _draw

    def _draw(self, image, draw, real_box) -> None:
        draw.rectangle(real_box.PIL_rect, fill=self.BG_COLOR)

        if self._active:
            rx0, rx1 = real_box.x0, real_box.x1
            y0 = real_box.y0 + 1  # inside top rule
            y1 = real_box.y1 - 2  # inside bottom rule (PIL rect is inclusive)
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

    # ── tick ─────────────────────────────────────────────────────────────────

    def tick(self, cents: float | None) -> None:
        now = time.monotonic()
        dt = min(now - self._last_tick, 0.5)  # cap dt to avoid jumps after pause
        self._last_tick = now

        if cents is None:
            if self._active:
                self._active = False
                self._zone = "accent"
                self._stripe_color = _ACCENT_COLOR
                self.refresh()
            return

        if not self._active:
            self._active = True
            self.refresh()
            return

        new_zone: Zone = _cents_zone(cents)
        if new_zone != self._zone:
            self._zone = new_zone
            self._stripe_color = _zone_color(cents)
            self.refresh()
            return

        if self._zone == "in_tune":
            return  # Frozen — zero SPI writes

        # Velocity: STRIPE_P px/s at ±50¢ → K px/s per cent
        K = (self.STRIPE_P / 50.0) * self.VELOCITY_SCALE
        velocity = max(-50.0, min(50.0, cents)) * K
        old_phase_int = int(self._phase)
        self._phase = (self._phase + velocity * dt) % float(_W)
        k = int(self._phase) - old_phase_int

        if k == 0:
            return

        if abs(k) >= self.STRIPE_W:
            self.refresh()
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

        try:
            note_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 56)
            info_font = ImageFont.truetype("DejaVuSans.ttf", 20)
            hint_font = ImageFont.truetype("DejaVuSans.ttf", 11)
        except OSError:
            logging.warning("tuner: DejaVu fonts not found, using default")
            note_font = ImageFont.load_default()
            info_font = ImageFont.load_default()
            hint_font = ImageFont.load_default()

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
        self._hint_drawn = False

    def input_event(self, event) -> bool:
        if event in (InputEvent.CLICK, InputEvent.LONG_CLICK):
            self._on_dismiss()
            return True
        return False

    def tick(self) -> None:
        if not self._hint_drawn:
            self._hint.refresh()
            self._hint_drawn = True
        reading = self._engine.get_reading()
        if reading is not None and time.monotonic() - reading.ts > self.STALE_SECS:
            reading = None
        self._header.tick(reading)
        self._strobe.tick(reading.cents if reading else None)
