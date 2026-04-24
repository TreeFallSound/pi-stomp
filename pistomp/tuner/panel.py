import logging
import time
from typing import Callable

from PIL import ImageFont

from uilib.box import Box
from uilib.misc import InputEvent
from uilib.panel import Panel
from uilib.widget import Widget

from pistomp.tuner.engine import TunerEngine, TunerReading

_W = 320  # display width

# ── NoteWidget ──────────────────────────────────────────────────────────────


class NoteWidget(Widget):
    """Big note name (e.g. 'A4') at the top of the tuner panel."""

    def __init__(self, box: Box, font, **kwargs) -> None:
        super().__init__(box=box, **kwargs)
        self._font = font
        self._text: str | None = None

    def _draw(self, image, draw, real_box) -> None:
        if self._text:
            draw.text(
                (real_box.x0 + 8, real_box.y0 + 4),
                self._text,
                font=self._font,
                fill=self.fgnd_color,
            )

    def tick(self, note: str | None) -> None:
        if note == self._text:
            return
        self._text = note
        self.refresh()


# ── FreqWidget ───────────────────────────────────────────────────────────────


class FreqWidget(Widget):
    """Frequency + cents readout at the bottom of the tuner panel."""

    def __init__(self, box: Box, font, **kwargs) -> None:
        super().__init__(box=box, **kwargs)
        self._font = font
        self._text: str | None = None

    def _draw(self, image, draw, real_box) -> None:
        if self._text:
            draw.text(
                (real_box.x0 + 8, real_box.y0 + 6),
                self._text,
                font=self._font,
                fill=self.fgnd_color,
            )

    def tick(self, reading: TunerReading | None) -> None:
        text = f"{reading.freq_hz:.1f} Hz   {reading.cents:+.1f}\u00a2" if reading is not None else None
        if text == self._text:
            return
        self._text = text
        self.refresh()


# ── StrobeWidget ─────────────────────────────────────────────────────────────


class StrobeWidget(Widget):
    """Sparse strobe: 6 accent stripes scrolling horizontally.

    Only trailing and leading edge columns are written to the LCD each tick;
    background pixels are never touched after initial setup.
    """

    STRIPE_W = 8
    STRIPE_P = 53
    N_STRIPES = 6
    IN_TUNE_THRESH = 2.0  # cents
    ACCENT_COLOR = (255, 180, 0)
    IN_TUNE_COLOR = (0, 200, 0)
    BG_COLOR = (20, 20, 20)
    RULE_COLOR = (80, 80, 80)
    VELOCITY_SCALE = 5.0

    def __init__(self, box: Box, **kwargs) -> None:
        kwargs.setdefault("bkgnd_color", StrobeWidget.BG_COLOR)
        super().__init__(box=box, **kwargs)
        self._phase: float = 0.0
        self._in_tune = False
        self._stripe_color = self.ACCENT_COLOR
        self._last_tick = time.monotonic()
        self._active = False

    # ── drawing ──────────────────────────────────────────────────────────────

    def _draw_erase(self, image, draw, box) -> None:
        pass  # We handle erasing inside _draw

    def _draw(self, image, draw, real_box) -> None:
        # Fill region with background
        draw.rectangle(real_box.PIL_rect, fill=self.BG_COLOR)

        if self._active:
            rx0, rx1 = real_box.x0, real_box.x1
            y0 = real_box.y0 + 1  # inside top rule
            y1 = real_box.y1 - 2  # inside bottom rule (PIL rect is inclusive)
            if y0 <= y1:
                for i in range(self.N_STRIPES):
                    sx = (int(self._phase) + i * self.STRIPE_P) % _W
                    self._paint_overlap(draw, sx, self.STRIPE_W, rx0, rx1, y0, y1)

        # Rules — always redrawn when the column touches widget top/bottom
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
                self._in_tune = False
                self._stripe_color = self.ACCENT_COLOR
                self.refresh()
            return

        if not self._active:
            self._active = True
            self.refresh()
            return

        was_in_tune = self._in_tune
        now_in_tune = abs(cents) <= self.IN_TUNE_THRESH

        if now_in_tune != was_in_tune:
            self._in_tune = now_in_tune
            self._stripe_color = self.IN_TUNE_COLOR if now_in_tune else self.ACCENT_COLOR
            self.refresh()
            return

        if now_in_tune:
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
            # Large jump (dt clamping missed): fall back to full repaint
            self.refresh()
            return

        ak = abs(k)
        for i in range(self.N_STRIPES):
            old_sx = (old_phase_int + i * self.STRIPE_P) % _W
            if k > 0:
                tail_x = old_sx  # left edge of old stripe → now bg
                lead_x = (old_sx + self.STRIPE_W) % _W  # right edge of new stripe
            else:
                tail_x = (old_sx + self.STRIPE_W - ak) % _W  # right edge of old → now bg
                lead_x = (old_sx - ak) % _W  # left edge of new stripe
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
            note_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 48)
            freq_font = ImageFont.truetype("DejaVuSans.ttf", 20)
        except OSError:
            logging.warning("tuner: DejaVu fonts not found, using default")
            note_font = ImageFont.load_default()
            freq_font = ImageFont.load_default()

        self._note = NoteWidget(box=Box.xywh(0, 0, _W, 60), font=note_font, parent=self)
        self._strobe = StrobeWidget(box=Box.xywh(0, 70, _W, 100), parent=self)
        self._freq = FreqWidget(box=Box.xywh(0, 180, _W, 50), font=freq_font, parent=self)

    def input_event(self, event) -> bool:
        if event in (InputEvent.CLICK, InputEvent.LONG_CLICK):
            self._on_dismiss()
            return True
        return False

    def tick(self) -> None:
        reading = self._engine.get_reading()
        if reading is not None and time.monotonic() - reading.ts > self.STALE_SECS:
            reading = None
        self._note.tick(reading.note if reading else None)
        self._strobe.tick(reading.cents if reading else None)
        self._freq.tick(reading)
