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


_ITEM_PAD = 1  # px of padding around each text bbox — absorbs anti-aliasing fringe

# TODO: move this into uilib
class _TextItem:
    """One independent text label: tracks what was rendered and where.

    render() is called from a full _draw pass (panel mount / full refresh) and
    simply draws the text, recording the padded bbox for future updates.

    update() is called from tick() and does a surgical clear-then-draw:
    it draws bg over the union of old + new bboxes and redraws only the text,
    then pushes just that region to the LCD via the widget's _focus/_unfocus.
    The panel bg is NEVER cleared by the header widget — only by the panel mount.
    """

    def __init__(self, bg_color: Color) -> None:
        self._bg = bg_color
        self._text: str | None = None
        self._bbox: Box | None = None

    def _measure(self, font, text: str, x: int, y: int) -> Box:
        try:
            tb = font.getbbox(text)
        except Exception:
            tb = (0, 0, len(text) * 10, 20)
        return Box(x + tb[0] - _ITEM_PAD, y + tb[1] - _ITEM_PAD,
                   x + tb[2] + _ITEM_PAD, y + tb[3] + _ITEM_PAD)

    def render(self, draw, font, color: Color, x: int, y: int,
               text: str | None) -> None:
        """Draw text into an already-obtained draw context; record bbox."""
        if text:
            draw.text((x, y), text, font=font, fill=color)
            self._bbox = self._measure(font, text, x, y)
        else:
            self._bbox = None
        self._text = text

    def update(self, widget: Widget, font, color: Color, x: int, y: int,
               text: str | None) -> None:
        """Surgical update: clear old bbox, draw new text, push to LCD."""
        if text == self._text:
            return
        new_bbox = self._measure(font, text, x, y) if text else None
        if self._bbox and new_bbox:
            dirty = self._bbox.union(new_bbox)
        else:
            dirty = self._bbox or new_bbox
        self._text = text
        self._bbox = new_bbox
        if dirty is None:
            return
        image, draw, _ = widget._focus(dirty)
        if image is None:
            return
        draw.rectangle(dirty.PIL_rect, fill=self._bg)
        if text and new_bbox:
            draw.text((x, y), text, font=font, fill=color)
        widget._unfocus(dirty)


class TunerHeaderWidget(Widget):
    """Note name (left); cents and Hz stacked right-aligned on the right."""

    HZ_COLOR: Color = (90, 90, 90)

    def __init__(self, box: Box, note_font, info_font, **kwargs) -> None:
        super().__init__(box=box, **kwargs)
        self._note_font = note_font
        self._info_font = info_font
        bg = kwargs.get("bkgnd_color", (0, 0, 0))
        self._note_item = _TextItem(bg)
        self._cents_item = _TextItem(bg)
        self._hz_item = _TextItem(bg)
        self._cents_color: Color = _ACCENT_COLOR

    # ── drawing ───────────────────────────────────────────────────────────────

    def _draw_erase(self, image, draw, box) -> None:
        pass  # panel bg is drawn once at mount; we never clear the full header

    def _draw(self, image, draw, real_box) -> None:
        """Full redraw — only happens at panel mount. Items record their bboxes."""
        bx = self.box
        if bx is None:
            return
        h = bx.height
        mid_y = bx.y0 + h // 2
        note = self._note_item._text
        cents = self._cents_item._text   # already a formatted string or None
        hz = self._hz_item._text

        if note:
            try:
                nb = self._note_font.getbbox(note)
                ny = bx.y0 + (h - (nb[3] - nb[1])) // 2 - nb[1]
            except Exception:
                ny = bx.y0 + 2
            self._note_item.render(draw, self._note_font, self.fgnd_color,
                                   bx.x0 + 8, ny, note)

        if cents:
            try:
                cb = self._info_font.getbbox(cents)
                tw, th = cb[2], cb[3] - cb[1]
            except Exception:
                tw, th = 60, 16
            cy = bx.y0 + (h // 2 - th) // 2 + 4
            # color was stored at tick time; retrieve it from the cached text
            # by re-deriving cents value from the stored string is awkward, so
            # we pass fgnd_color and rely on _zone_color being called in tick.
            self._cents_item.render(draw, self._info_font,
                                    self._cents_color, bx.x1 - tw - 8, cy, cents)

        if hz:
            try:
                hb = self._info_font.getbbox(hz)
                tw, th = hb[2], hb[3] - hb[1]
            except Exception:
                tw, th = 60, 16
            hy = mid_y + (h // 2 - th) // 2 - 4
            self._hz_item.render(draw, self._info_font, self.HZ_COLOR,
                                 bx.x1 - tw - 8, hy, hz)

    # ── tick ──────────────────────────────────────────────────────────────────

    def tick(self, reading: TunerReading | None) -> None:
        bx = self.box
        if bx is None:
            return
        h = bx.height
        mid_y = bx.y0 + h // 2

        note = reading.note if reading else None
        cents_val = round(reading.cents, 1) if reading else None
        hz_val = round(reading.freq_hz, 1) if reading else None

        # Note — left, vertically centred
        if note:
            try:
                nb = self._note_font.getbbox(note)
                ny = bx.y0 + (h - (nb[3] - nb[1])) // 2 - nb[1]
            except Exception:
                ny = bx.y0 + 2
            self._note_item.update(self, self._note_font, self.fgnd_color,
                                   bx.x0 + 8, ny, note)
        else:
            self._note_item.update(self, self._note_font, self.fgnd_color,
                                   bx.x0 + 8, bx.y0, None)

        # Cents — top-right
        if cents_val is not None:
            arrow = "\u25b4" if cents_val >= 0 else "\u25be"
            cents_text = f"{abs(cents_val):.1f} {arrow}"
            color = _zone_color(cents_val)
            try:
                cb = self._info_font.getbbox(cents_text)
                tw, th = cb[2], cb[3] - cb[1]
            except Exception:
                tw, th = 60, 16
            cy = bx.y0 + (h // 2 - th) // 2 + 4
            self._cents_color = color
            self._cents_item.update(self, self._info_font, color,
                                    bx.x1 - tw - 8, cy, cents_text)
        else:
            self._cents_item.update(self, self._info_font, self.fgnd_color,
                                    bx.x0, bx.y0, None)

        # Hz — bottom-right
        if hz_val is not None:
            hz_text = f"{hz_val:.1f} hz"
            try:
                hb = self._info_font.getbbox(hz_text)
                tw, th = hb[2], hb[3] - hb[1]
            except Exception:
                tw, th = 60, 16
            hy = mid_y + (h // 2 - th) // 2 - 4
            self._hz_item.update(self, self._info_font, self.HZ_COLOR,
                                 bx.x1 - tw - 8, hy, hz_text)
        else:
            self._hz_item.update(self, self._info_font, self.HZ_COLOR,
                                 bx.x0, bx.y0, None)


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
        self._stripe_color: Color = _ACCENT_COLOR
        self._last_tick = time.monotonic()
        self._has_reading = False

    # ── drawing ──────────────────────────────────────────────────────────────

    def _draw_erase(self, image, draw, box) -> None:
        pass  # We handle erasing inside _draw

    def _draw(self, image, draw, real_box) -> None:
        draw.rectangle(real_box.PIL_rect, fill=self.BG_COLOR)

        if self._has_reading:
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

    def _refresh_stripes_at(self, phase_int: int) -> None:
        """Mark the N stripe columns at the given phase as dirty.

        Each column is STRIPE_W wide and full widget height. _draw will repaint
        bg + (if _has_reading) the stripe in _stripe_color, so this works for
        paint-on, paint-off, and colour-change transitions without touching
        the gaps between stripes.
        """
        for i in range(self.N_STRIPES):
            sx = (phase_int + i * self.STRIPE_P) % _W
            self._refresh_col(sx, self.STRIPE_W)

    # ── tick ─────────────────────────────────────────────────────────────────

    def tick(self, cents: float | None) -> None:
        now = time.monotonic()
        dt = min(now - self._last_tick, 0.5)  # cap dt to avoid jumps after pause
        self._last_tick = now

        if cents is None:
            if self._has_reading:
                self._has_reading = False
                self._zone = "accent"
                self._stripe_color = _ACCENT_COLOR
                # Erase stripes at their last positions; bg + rules remain.
                self._refresh_stripes_at(int(self._phase))
            return

        if not self._has_reading:
            self._has_reading = True
            # Initial paint — bg and rules were drawn at panel mount; only
            # the stripe columns need to light up.
            self._refresh_stripes_at(int(self._phase))
            return

        new_zone: Zone = _cents_zone(cents)
        if new_zone != self._zone:
            self._zone = new_zone
            self._stripe_color = _zone_color(cents)
            # Colour change — stripes haven't moved, just repaint them.
            self._refresh_stripes_at(int(self._phase))
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

        # Large phase jump (≥ stripe width): old and new stripe positions
        # don't overlap, so repaint both sets of columns in full. Still far
        # cheaper than a full-widget refresh.
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
