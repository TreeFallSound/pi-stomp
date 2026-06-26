"""Full-screen LCD panel for the NAM Capture pedalboard marker.

Two distinct layouts:

  SETUP VIEW (IDLE)
  ┌─ NAM Capture ─────────────────────────────────┐
  │ Name: [ my-fender-clean                     ] │
  │ ~3:10 · T3K-sweep-v3                          │
  │   ╭──────────╮           ╭──────────╮         │
  │   │  INPUT   │           │  HEADPH  │         │
  │   │   GAIN   │           │   VOL    │         │
  │   │  (knob)  │           │  (knob)  │         │
  │   │  -6.0 dB │           │ -12.0 dB │         │
  │   ╰──────────╯           ╰──────────╯         │
  │ [ Close ]                         [ Start ]   │
  └───────────────────────────────────────────────┘

  CAPTURE VIEW (CAPTURING / DONE / FAILED / ABORTED)
  ┌─ ● NAM Capture              my-fender-clean ──┐
  │  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░  │
  │  0:52                                  −1:18  │
  │                                               │
  │ OUT ████████████░░░░░░  -9.1dB                │
  │  IN ████████████████░░  -3.1dB                │
  │                              [ Abort ]        │
  └───────────────────────────────────────────────┘

Levels freeze on failure (FAILED/ABORTED) so the screen serves as a
diagnostic snapshot. Enc 2 (tweak) controls input gain; enc 3 (vol)
controls headphone volume — in both views (setup shows knobs; capture
adjusts silently).
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Callable

from uilib.box import Box
from uilib.config import Config
from uilib.glyphs import ArcRingGlyph
from uilib.label import Label
from uilib.misc import TextHAlign, get_text_bbox, get_text_size
from uilib.paint import PaintContext
from uilib.pygame_init import font as _make_font
from uilib.text import Button, TextWidget
from uilib.widget import Widget

import common.token as Token
import pistomp.switchstate as switchstate

from uilib import profiling

from pistomp.fullscreen_panel import FullscreenPanel
from pistomp.input.event import ControllerEvent, EncoderEvent, SwitchEvent, SwitchEventKind
from pistomp.nam import routing
from pistomp.nam.engine import CaptureState, NamCaptureEngine
from pistomp.nam.wavio import wav_duration

_W = 320
_H = 240

_FONTS_DIR = Path(__file__).resolve().parents[2] / "fonts"
_REAMP_WAV = Path(__file__).resolve().parents[2] / "setup" / "nam" / "T3K-sweep-v3.wav"

# ── Layout constants ──────────────────────────────────────────────────────────

# Setup view
_TITLE_H = 26
_NAME_Y = 30
_NAME_H = 28
_KNOB_Y = 82
_KNOB_H = 114
_KNOB_W = 148

# Chrome row — shared between views
_BTN_GAP = 2
_BTN_H = 28
_BTN_Y = _H - _BTN_H - _BTN_GAP  # 210
_BTN_W = (_W - 4 * _BTN_GAP) // 3  # 104
_BTN_X_CLOSE = _BTN_GAP
_BTN_X_ACTION = _BTN_GAP * 3 + _BTN_W * 2

# Capture view
_CAP_HDR_H = 22
_REEL_Y = _CAP_HDR_H
_REEL_H = 110
_ERR_Y = _REEL_Y + _REEL_H + 2  # 134 — feedback text above meters
_METER_H = 22
_METER_OUT_Y = _ERR_Y + _METER_H  # 156
_METER_IN_Y = _METER_OUT_Y + _METER_H + 2  # 180

# ── Colour palette ────────────────────────────────────────────────────────────

# Progress bar colour stops (position 0.0–1.0 along bar width)
_BAR_STOPS: list[tuple[float, tuple[int, int, int]]] = [
    (0.00, (0, 200, 75)),
    (0.35, (120, 215, 0)),
    (0.65, (230, 148, 0)),
    (1.00, (215, 55, 10)),
]
_BAR_DIM = 0.13  # brightness of unfilled segments

# Status LED
_LED_IDLE = (70, 70, 78)
_LED_CAPTURING = (0, 200, 80)
_LED_DONE = (0, 210, 90)
_LED_FAILED = (230, 70, 70)
_LED_ABORTED = (160, 90, 20)
_LED_OFF = (14, 14, 17)

# Level meters
_SEG_GREEN = (0, 175, 55)
_SEG_YELLOW = (195, 165, 0)
_SEG_RED = (215, 55, 40)
_SEG_OFF = (16, 20, 14)
_METER_LABEL_FG = (110, 110, 118)
_METER_VALUE_FG = (155, 155, 165)
_METER_CLIP_FG = (220, 60, 50)

# Knobs
_KNOB_ARC_FG = (195, 135, 40)  # amber — filled arc
_KNOB_ARC_BG = (38, 30, 14)  # dim warm dark — empty arc track
_KNOB_TIP = (255, 210, 80)  # bright amber — tip dot
_KNOB_LABEL_FG = (115, 115, 125)
_KNOB_VALUE_FG = (175, 175, 195)

# Misc
_DIM = (75, 75, 82)
_ERR_FG = (225, 85, 85)
_HEADER_FG = (130, 130, 140)
_HEADER_NAME_FG = (100, 100, 110)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _fmt_time(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}"


def _centred_x(text: str, font, width: int) -> int:
    bb = get_text_bbox(text, font)
    return (width - (bb[2] - bb[0])) // 2 - bb[0]


# ── Custom widgets ────────────────────────────────────────────────────────────


class KnobWidget(Widget):
    """Arc-ring rotary display for audio parameter control."""

    _VALUE_H = 20

    def __init__(
        self,
        box: Box,
        label: str,
        min_val: float,
        max_val: float,
        default_font,
        caption_font,
        parent: Widget,
    ) -> None:
        super().__init__(box=box, bkgnd_color=(0, 0, 0), parent=parent)
        self._label = label
        self._min_val = min_val
        self._max_val = max_val
        self._default_font = default_font
        self._caption_font = caption_font
        self._value = min_val
        arc_area_h = box.height - self._VALUE_H
        self._arc_r = min(box.width // 2 - 10, arc_area_h // 2 - 8)
        self._arc_tip_r = 7.0
        self._arc = ArcRingGlyph(self._arc_r, tip_radius=self._arc_tip_r)

    def set_value(self, value: float) -> None:
        new_val = max(self._min_val, min(self._max_val, value))
        if new_val == self._value:
            return
        old_t = self._t()
        self._value = new_val
        new_t = self._t()
        self.refresh(self._dirty_rect(old_t, new_t))

    def _t(self) -> float:
        if self._max_val == self._min_val:
            return 0.0
        return max(0.0, min(1.0, (self._value - self._min_val) / (self._max_val - self._min_val)))

    def _tip_rect_abs(self, t: float) -> Box:
        """Absolute bounding box of the tip dot at value fraction t."""
        cx = self.box.x0 + self.box.width // 2
        cy = self.box.y0 + (self.box.height - self._VALUE_H) // 2
        rad = math.radians(210.0 + t * 300.0)
        tx = cx + self._arc_r * math.sin(rad)
        ty = cy - self._arc_r * math.cos(rad)
        pad = int(self._arc_tip_r) + 1
        return Box.xywh(int(tx) - pad, int(ty) - pad, 2 * pad + 1, 2 * pad + 1)

    def _dirty_rect(self, old_t: float, new_t: float) -> Box:
        """Tight absolute dirty rect for a value change from old_t to new_t.

        For typical encoder ticks (< 10 % range) only the two tip dot areas
        and the value-text strip need repainting — a ~5x reduction in pixels
        pushed over SPI vs the full widget, keeping the push inline at all
        supported SPI speeds including 33 MHz.  Large jumps fall back to the
        full widget so the changed arc segment is never left stale.
        """
        w, h = self.box.width, self.box.height
        value_rect = Box.xywh(self.box.x0, self.box.y0 + h - self._VALUE_H, w, self._VALUE_H)
        if abs(new_t - old_t) < 0.10:
            return self._tip_rect_abs(old_t).union(self._tip_rect_abs(new_t)).union(value_rect)
        return self.box

    def _draw(self, ctx: PaintContext) -> None:
        w, h = ctx.width, ctx.height
        cx = w // 2
        cy = (h - self._VALUE_H) // 2

        surf = self._arc.render(self._t(), _KNOB_ARC_FG, _KNOB_ARC_BG, _KNOB_TIP)
        hs = self._arc.half_size
        ctx.paste(surf, (cx - hs, cy - hs))

        ctx.draw_text((cx, cy), self._label, fill=_KNOB_LABEL_FG, font=self._caption_font, anchor="mm")

        value_text = f"{self._value:.1f} dB"
        ctx.draw_text(
            (cx, h - self._VALUE_H // 2), value_text, fill=_KNOB_VALUE_FG, font=self._default_font, anchor="mm"
        )


class ProgressBarWidget(Widget):
    """Segmented colour-gradient progress bar with elapsed/remaining time labels."""

    _MARGIN = 12        # left/right inset
    _BAR_Y = 30         # top of bar within widget
    _BAR_H = 30         # bar height
    _LABEL_GAP = 10     # gap between bar bottom and label top
    _N_SEGS = 40        # number of colour segments
    _SEG_GAP = 2        # gap between segments in pixels

    def __init__(self, box: Box, total_seconds: float, font, caption_font, parent: Widget) -> None:
        super().__init__(box=box, bkgnd_color=(0, 0, 0), parent=parent)
        self._total = total_seconds
        self._progress = 0.0
        self._frozen = False
        self._elapsed = 0.0
        self._remaining = total_seconds
        self._font = font
        self._caption_font = caption_font
        inner_w = box.width - 2 * self._MARGIN
        self._seg_w = max(1, (inner_w - (self._N_SEGS - 1) * self._SEG_GAP) // self._N_SEGS)

    def set_progress(self, progress: float) -> None:
        if self._frozen:
            return
        p = max(0.0, min(1.0, progress))
        old_filled = int(self._progress * self._N_SEGS)
        self._progress = p
        self._elapsed = p * self._total
        self._remaining = self._total - self._elapsed
        if int(p * self._N_SEGS) != old_filled:
            self.refresh()

    def freeze(self) -> None:
        self._frozen = True

    def set_done(self) -> None:
        self._progress = 1.0
        self._elapsed = self._total
        self._remaining = 0.0
        self._frozen = True

    def reset(self) -> None:
        self._progress = 0.0
        self._elapsed = 0.0
        self._remaining = self._total
        self._frozen = False

    def advance_rotation(self, dt: float) -> None:
        pass

    @staticmethod
    def _color_at(t: float) -> tuple[int, int, int]:
        stops = _BAR_STOPS
        if t <= stops[0][0]:
            return stops[0][1]
        if t >= stops[-1][0]:
            return stops[-1][1]
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                f = (t - t0) / (t1 - t0)
                return (
                    int(c0[0] + f * (c1[0] - c0[0])),
                    int(c0[1] + f * (c1[1] - c0[1])),
                    int(c0[2] + f * (c1[2] - c0[2])),
                )
        return stops[-1][1]

    def _draw(self, ctx: PaintContext) -> None:
        with profiling.measure("nam.bar._draw"):
            n = self._N_SEGS
            filled = int(self._progress * n)
            sw = self._seg_w
            bx = self._MARGIN
            by = self._BAR_Y
            ctx.fill((0, 0, 0))

            for i in range(n):
                t = i / (n - 1) if n > 1 else 0.0
                r, g, b = self._color_at(t)
                if i < filled:
                    color: tuple[int, int, int] = (r, g, b)
                else:
                    color = (int(r * _BAR_DIM), int(g * _BAR_DIM), int(b * _BAR_DIM))
                ctx.draw_rectangle(Box.xywh(bx + i * (sw + self._SEG_GAP), by, sw, self._BAR_H), fill=color)

            label_y = by + self._BAR_H + self._LABEL_GAP
            right_x = ctx.width - self._MARGIN

            elapsed_str = _fmt_time(self._elapsed)
            ctx.draw_text((bx, label_y), elapsed_str, fill=(130, 118, 80), font=self._font)

            remaining_str = f"−{_fmt_time(self._remaining)}"
            rw, _ = get_text_size(remaining_str, self._font)
            ctx.draw_text((right_x - rw, label_y), remaining_str, fill=(205, 180, 110), font=self._font)


class LevelMeter(Widget):
    """Segmented horizontal VU meter with dB readout and clip indicator."""

    _SEG_COUNT = 19
    _SEG_GREEN_MAX = 10
    _SEG_YELLOW_MAX = 15
    _LABEL_W = 36
    _BAR_X = 42
    _SEG_W = 10
    _SEG_GAP = 1
    # Total bar width: 19*10 + 18*1 = 208px → x=42 to x=249
    _VALUE_CX = 288  # center of value region x=252..320

    def __init__(self, box: Box, label: str, default_font, caption_font, parent: Widget) -> None:
        super().__init__(box=box, bkgnd_color=(0, 0, 0), parent=parent)
        self._label = label
        self._default_font = default_font
        self._caption_font = caption_font
        self._level_db: float | None = None
        self._clipping: bool = False

    def set_level(self, db: float | None) -> None:
        self._level_db = db

    def set_clip(self, clipping: bool) -> None:
        self._clipping = clipping

    def _db_to_segments(self, db: float) -> int:
        return max(0, min(self._SEG_COUNT, int((db + 60.0) / 60.0 * self._SEG_COUNT + 0.5)))

    def _draw(self, ctx: PaintContext) -> None:
        h = ctx.height
        bar_y = (h - 10) // 2
        bar_h = 10

        tw, _ = get_text_size(self._label, self._caption_font)
        ctx.draw_text(
            (self._LABEL_W - 2 - tw // 2, h // 2),
            self._label,
            fill=_METER_LABEL_FG,
            font=self._caption_font,
            anchor="mm",
        )

        if self._clipping:
            n_segs = self._SEG_COUNT
        elif self._level_db is not None:
            n_segs = self._db_to_segments(self._level_db)
        else:
            n_segs = 0

        for i in range(self._SEG_COUNT):
            sx = self._BAR_X + i * (self._SEG_W + self._SEG_GAP)
            lit = i < n_segs
            if not lit:
                color = _SEG_OFF
            elif self._clipping:
                color = _SEG_RED
            elif i < self._SEG_GREEN_MAX:
                color = _SEG_GREEN
            elif i < self._SEG_YELLOW_MAX:
                color = _SEG_YELLOW
            else:
                color = _SEG_RED
            ctx.draw_rectangle(Box.xywh(sx, bar_y, self._SEG_W, bar_h), fill=color)

        if self._clipping:
            text, color = "CLIP", _METER_CLIP_FG
        elif self._level_db is not None:
            sign = "+" if self._level_db >= 0 else ""
            text, color = f"{sign}{self._level_db:.1f}dB", _METER_VALUE_FG
        else:
            text, color = "---", _DIM

        ctx.draw_text((self._VALUE_CX, h // 2), text, fill=color, font=self._default_font, anchor="mm")


class StatusLed(Widget):
    """10×10 status indicator dot with phosphor-decay fade."""

    _DECAY_RATE = 4.77  # e-folding rate → half-life ≈ 145ms
    _REDRAW_THRESHOLD = 0.01

    def __init__(self, x: int, y: int, parent: Widget) -> None:
        super().__init__(Box.xywh(x, y, 10, 10), bkgnd_color=(0, 0, 0), parent=parent)
        self._led_color: tuple[int, int, int] = _LED_IDLE
        self._brightness: float = 1.0

    def set_color(self, color: tuple[int, int, int]) -> None:
        self._led_color = color
        self._brightness = 1.0

    def flash(self) -> None:
        self._brightness = 1.0
        self.refresh()

    def decay_step(self, dt: float) -> None:
        if self._brightness < self._REDRAW_THRESHOLD:
            return
        new_b = self._brightness * math.exp(-self._DECAY_RATE * dt)
        self._brightness = new_b
        self.refresh()

    def _draw(self, ctx: PaintContext) -> None:
        b = self._brightness
        r, g, c_b = self._led_color
        color: tuple[int, int, int] = (
            max(0, min(255, int(r * b))),
            max(0, min(255, int(g * b))),
            max(0, min(255, int(c_b * b))),
        )
        ctx.draw_ellipse(ctx.bounds, fill=color)


# ── Main panel ────────────────────────────────────────────────────────────────


class NamCapturePanel(FullscreenPanel):
    """Full-screen panel for NAM capture. Owns the engine lifecycle."""

    def __init__(
        self,
        output_dir: str | Path,
        on_dismiss: Callable[[], None],
        reamp_wav: Path = _REAMP_WAV,
        handler=None,
    ) -> None:
        super().__init__()
        self._on_dismiss = on_dismiss
        self._handler = handler
        self._engine = self._create_engine(output_dir, reamp_wav)
        self._last_state = CaptureState.IDLE
        self._last_blink: float = 0.0
        self._last_tick: float | None = None
        self._meter_tick: int = 0
        self._in_capture_view: bool = False
        self._pending_path_shown: bool = False
        self._duration = wav_duration(reamp_wav)
        self._gain_val: float = -10.0
        self._vol_val: float = -10.0
        self._saved_gain: float | None = None
        self._saved_vol: float | None = None

        font = Config().get_font("default")
        title_font = Config().get_font("default_title")
        self._caption_font = _make_font(str(_FONTS_DIR / "DejaVuSans-Bold.ttf"), 12)

        # ── SETUP VIEW ────────────────────────────────────────────────────────

        _, title_h = get_text_size("NAM Capture", title_font)
        self._title_bar = TextWidget(
            box=Box.xywh(0, 0, _W, _TITLE_H),
            text="NAM Capture",
            font=title_font,
            text_halign=TextHAlign.CENTRE,
            h_margin=0,
            v_margin=max(0, (_TITLE_H - title_h) // 2),
            outline=0,
            bkgnd_color=Config().get_color("default_title_bkgnd"),
            fgnd_color=Config().get_color("default_title_fgnd"),
            parent=self,
        )

        self._setup_name_label = Label(10, _NAME_Y + 7, font, parent=self)
        self._setup_name_label.set_text("Name:", (160, 160, 160))

        self._name_btn = Button(
            box=Box.xywh(64, _NAME_Y, _W - 72, _NAME_H),
            text="capture",
            font=font,
            outline_radius=3,
            edit_message="Capture name:",
            parent=self,
        )

        self._knob_gain = KnobWidget(
            box=Box.xywh(8, _KNOB_Y, _KNOB_W, _KNOB_H),
            label="IN",
            min_val=-19.75,
            max_val=12.0,
            default_font=font,
            caption_font=self._caption_font,
            parent=self,
        )
        self._knob_vol = KnobWidget(
            box=Box.xywh(_W - _KNOB_W - 8, _KNOB_Y, _KNOB_W, _KNOB_H),
            label="OUT",
            min_val=-25.75,
            max_val=6.0,
            default_font=font,
            caption_font=self._caption_font,
            parent=self,
        )

        self._btn_setup_close = Button(
            box=Box.xywh(_BTN_X_CLOSE, _BTN_Y, _BTN_W, _BTN_H),
            text="Close",
            font=font,
            outline_radius=4,
            parent=self,
            action=lambda *_: on_dismiss(),
        )
        self._btn_start = Button(
            box=Box.xywh(_BTN_X_ACTION, _BTN_Y, _BTN_W, _BTN_H),
            text=f"Start ({_fmt_time(self._duration)})",
            font=font,
            outline_radius=4,
            parent=self,
            action=lambda *_: self._on_start(),
        )

        self._setup_group = [
            self._title_bar,
            self._setup_name_label,
            self._name_btn,
            self._knob_gain,
            self._knob_vol,
            self._btn_setup_close,
            self._btn_start,
        ]
        self.add_sel_widget(self._name_btn)
        self.add_sel_widget(self._btn_setup_close)
        self.add_sel_widget(self._btn_start)

        # ── CAPTURE VIEW ──────────────────────────────────────────────────────

        # Header strip (y=0-22 replaces title bar when in capture view)
        self._cap_hdr_bg = Widget(
            box=Box.xywh(0, 0, _W, _CAP_HDR_H),
            bkgnd_color=(0, 0, 0),
            parent=self,
        )
        self._status_led = StatusLed(6, 6, parent=self)
        self._cap_title_lbl = Label(20, 5, self._caption_font, parent=self)
        self._cap_title_lbl.set_text("NAM Capture", _HEADER_FG)
        self._cap_name_lbl = Label(0, 5, self._caption_font, parent=self)
        self._cap_name_lbl.set_text("", _HEADER_NAME_FG)

        self._reel = ProgressBarWidget(
            box=Box.xywh(0, _REEL_Y, _W, _REEL_H),
            total_seconds=self._duration,
            font=font,
            caption_font=self._caption_font,
            parent=self,
        )
        self._meter_out = LevelMeter(
            box=Box.xywh(0, _METER_OUT_Y, _W, _METER_H),
            label="OUT",
            default_font=font,
            caption_font=self._caption_font,
            parent=self,
        )
        self._meter_in = LevelMeter(
            box=Box.xywh(0, _METER_IN_Y, _W, _METER_H),
            label="IN",
            default_font=font,
            caption_font=self._caption_font,
            parent=self,
        )

        self._error_lbl = Label(0, _ERR_Y + 2, font, parent=self)

        self._btn_capture_close = Button(
            box=Box.xywh(_BTN_X_CLOSE, _BTN_Y, _BTN_W, _BTN_H),
            text="Close",
            font=font,
            outline_radius=4,
            parent=self,
            action=lambda *_: on_dismiss(),
        )
        self._btn_capture_right = Button(
            box=Box.xywh(_BTN_X_ACTION, _BTN_Y, _BTN_W, _BTN_H),
            text="Abort",
            font=font,
            outline_radius=4,
            parent=self,
            action=lambda *_: self._on_abort(),
        )
        # Full-width "Saved as …" button shown only in DONE state
        self._btn_done = Button(
            box=Box.xywh(_BTN_GAP, _BTN_Y, _W - 2 * _BTN_GAP, _BTN_H),
            text="Saved",
            font=font,
            outline_radius=4,
            parent=self,
            action=lambda *_: on_dismiss(),
        )

        self._capture_group = [
            self._cap_hdr_bg,
            self._status_led,
            self._cap_title_lbl,
            self._cap_name_lbl,
            self._reel,
            self._meter_out,
            self._meter_in,
            self._error_lbl,
            self._btn_capture_close,
            self._btn_capture_right,
            self._btn_done,
        ]

        # Initially hide the whole capture group
        for w in self._capture_group:
            w.hide(refresh=False)

        # Read initial values from hardware to seed the internal trackers
        self._init_knob_values()
        profiling.maybe_start()

        # Connect In2 → Out1 so the user can hear the amp while the panel is open.
        routing.connect_monitor()

    # ── Engine factory (overridden in tests) ──────────────────────────────────

    def _create_engine(self, output_dir: str | Path, reamp_wav: Path) -> NamCaptureEngine:
        return NamCaptureEngine(output_dir, reamp_wav=reamp_wav)

    # ── Panel lifecycle ───────────────────────────────────────────────────────

    def destroy(self) -> None:
        if self._handler is not None:
            self._handler.settings.set_setting(Token.NAM_CAPTURE_GAIN, self._gain_val)
            self._handler.settings.set_setting(Token.NAM_OUTPUT_VOL, self._vol_val)
            if self._saved_gain is not None:
                self._handler.audio_parameter_commit(self._handler.audiocard.CAPTURE_VOLUME, self._saved_gain)
            if self._saved_vol is not None:
                self._handler.audio_parameter_commit(self._handler.audiocard.MASTER, self._saved_vol)
        self._engine.stop()
        routing.disconnect_monitor()
        super().destroy()

    # ── Input handling ────────────────────────────────────────────────────────

    def handle(self, event: ControllerEvent) -> bool:
        cid = getattr(event.controller, "id", None)

        # Tweak1 (cid=1) mirrors the NAV encoder for the whole panel.
        if cid == 1 and self._handler is not None:
            if isinstance(event, EncoderEvent):
                self._handler.universal_encoder_select(event.rotations)
                return True
            if isinstance(event, SwitchEvent) and event.kind == SwitchEventKind.LONGPRESS:
                self._handler.universal_encoder_sw(switchstate.Value.LONGPRESSED)
                return True
            # PRESS falls through — modhandler already calls universal_encoder_sw(RELEASED).
            return False

        if not isinstance(event, EncoderEvent):
            return False
        if cid not in (2, 3):
            return False

        state = self._engine.state

        # Swallow enc 2/3 during capture — no level changes mid-recording.
        if state == CaptureState.CAPTURING:
            return True

        # Only on failure: pass through so the vanilla parameter overlay pops
        # up and the user can adjust levels before retrying.
        if state == CaptureState.FAILED:
            return False

        # IDLE: handle locally and update the on-screen knobs.
        # DONE/ABORTED: swallow — the setup view knobs aren't visible.
        if state == CaptureState.IDLE and self._handler is not None:
            steps = int(round(event.rotations * event.multiplier))
            self._nudge_audio(cid == 2, steps)
        return True

    # ── Polling ───────────────────────────────────────────────────────────────

    # Meters are the only content that changes every tick; coalesce them into
    # one SPI transfer. LED and progress bar refresh themselves when they change.
    _METER_ANIM_BOX = Box.xywh(0, _METER_OUT_Y, _W, _METER_IN_Y + _METER_H - _METER_OUT_Y)

    def tick(self) -> None:
        now = time.monotonic()
        dt = 0.0 if self._last_tick is None else now - self._last_tick
        self._last_tick = now

        state = self._engine.state
        profiling.set_context_tag(state.name.lower())

        with profiling.measure("nam.tick"):
            self._tick_body(now, dt, state)

    def _tick_body(self, now: float, dt: float, state: CaptureState) -> None:
        if state != self._last_state:
            self._apply_state(state)
            self._last_state = state

        if state == CaptureState.CAPTURING:
            if not self._pending_path_shown:
                pending = self._engine.pending_path
                if pending is not None:
                    self._update_cap_name_label(pending.name)
                    self._pending_path_shown = True

            self._reel.advance_rotation(dt)
            self._reel.set_progress(self._engine.progress())

            snap = self._engine.level_snapshot_db()
            if snap is not None:
                in_db, out_db = snap
                self._meter_in.set_level(in_db)
                self._meter_in.set_clip(in_db > -1.0)
                self._meter_out.set_level(out_db)
            else:
                self._meter_in.set_level(None)
                self._meter_out.set_level(None)

            if now - self._last_blink >= 1.0:
                self._last_blink = now
                self._status_led.flash()
            else:
                self._status_led.decay_step(dt)

            self._meter_tick += 1
            if self._meter_tick >= 10:
                self._meter_tick = 0
                self._meter_out.refresh()
                self._meter_in.refresh()

    # ── Private ───────────────────────────────────────────────────────────────

    def _on_start(self) -> None:
        if self._engine.state not in (
            CaptureState.IDLE,
            CaptureState.DONE,
            CaptureState.FAILED,
            CaptureState.ABORTED,
        ):
            return
        name = self._name_btn.text or "capture"
        self._update_cap_name_label(name)
        self._pending_path_shown = False
        self._engine.start(name)

    def _on_abort(self) -> None:
        """Show a confirmation dialog before aborting."""
        if self._engine.state != CaptureState.CAPTURING:
            return
        if self.parent is None:
            # No display (e.g. unit tests) — abort immediately.
            self._on_confirmed_abort()
            return
        from uilib.dialog import ConfirmDialog

        d = ConfirmDialog(
            self.parent,
            message="Discard this recording?",
            title="Abort Capture",
            on_confirm=self._on_confirmed_abort,
            confirm_text="Abort",
            cancel_text="Cancel",
        )
        self.parent.push_panel(d)

    def _on_confirmed_abort(self) -> None:
        """Abort the running capture and return to IDLE setup view."""
        self._engine.stop()
        self._engine.reset()

    def _on_reset(self) -> None:
        """Return to IDLE (setup view) from FAILED or ABORTED."""
        self._engine.reset()

    def _apply_state(self, state: CaptureState) -> None:
        if state == CaptureState.IDLE:
            if self._in_capture_view:
                self._switch_to_setup_view()
            return

        # All non-IDLE states live in the capture view
        if not self._in_capture_view:
            self._switch_to_capture_view()
        else:
            # Re-entering CAPTURING after DONE/FAILED/ABORTED (Restart/Retry)
            if state == CaptureState.CAPTURING:
                self._reel.reset()
                self._meter_in.set_level(None)
                self._meter_in.set_clip(False)
                self._meter_out.set_level(None)
                self._error_lbl.hide(refresh=False)

        self._configure_for_state(state)

    def _configure_for_state(self, state: CaptureState) -> None:
        """Update LED, buttons, and error label for *state* (capture view already shown)."""
        # LED
        led_colors = {
            CaptureState.CAPTURING: _LED_CAPTURING,
            CaptureState.DONE: _LED_DONE,
            CaptureState.FAILED: _LED_FAILED,
            CaptureState.ABORTED: _LED_ABORTED,
        }
        self._status_led.set_color(led_colors.get(state, _LED_IDLE))

        # Reel
        if state == CaptureState.DONE:
            self._reel.set_done()
        elif state in (CaptureState.FAILED, CaptureState.ABORTED):
            self._reel.freeze()

        # Error label — single short line, centred
        if state == CaptureState.FAILED:
            err = self._engine.error or "Capture failed"
            font = Config().get_font("default")
            self._error_lbl.set_text(err, _ERR_FG, x=_centred_x(err, font, _W))
            self._error_lbl.show(refresh=False)
            if "clip" in err.lower() or "amp" in err.lower():
                self._meter_in.set_clip(True)
        else:
            self._error_lbl.hide(refresh=False)

        # Buttons — rebuild sel list for capture view
        for w in (self._btn_capture_close, self._btn_capture_right, self._btn_done):
            if w in self.sel_list:
                self.del_sel_widget(w)
            w.hide(refresh=False)

        if state == CaptureState.CAPTURING:
            self._btn_capture_right.set_text("Abort")
            self._btn_capture_right.set_action(lambda *_: self._on_abort())
            self._btn_capture_right.show(refresh=False)
            self.add_sel_widget(self._btn_capture_right)

        elif state == CaptureState.DONE:
            path = self._engine.output_path
            name = path.name if path is not None else "capture.wav"
            self._btn_done.set_text(f"Saved as {name}")
            self._btn_done.show(refresh=False)
            self.add_sel_widget(self._btn_done)

        elif state == CaptureState.ABORTED:
            self._btn_capture_close.set_text("Back")
            self._btn_capture_close.set_action(lambda *_: self._on_reset())
            self._btn_capture_right.set_text("Restart")
            self._btn_capture_right.set_action(lambda *_: self._on_start())
            self._btn_capture_close.show(refresh=False)
            self._btn_capture_right.show(refresh=False)
            self.add_sel_widget(self._btn_capture_close)
            self.add_sel_widget(self._btn_capture_right)

        elif state == CaptureState.FAILED:
            self._btn_capture_close.set_text("Back")
            self._btn_capture_close.set_action(lambda *_: self._on_reset())
            self._btn_capture_right.set_text("Retry")
            self._btn_capture_right.set_action(lambda *_: self._on_start())
            self._btn_capture_close.show(refresh=False)
            self._btn_capture_right.show(refresh=False)
            self.add_sel_widget(self._btn_capture_close)
            self.add_sel_widget(self._btn_capture_right)

        self.refresh()

    def _switch_to_capture_view(self) -> None:
        for w in (self._name_btn, self._btn_setup_close, self._btn_start):
            self.del_sel_widget(w)
        for w in self._setup_group:
            w.hide(refresh=False)
        name = self._name_btn.text or "capture"
        self._update_cap_name_label(name)
        for w in self._capture_group:
            if w not in (self._error_lbl, self._btn_done):
                w.show(refresh=False)
        self._in_capture_view = True

    def _switch_to_setup_view(self) -> None:
        for w in (self._btn_capture_close, self._btn_capture_right, self._btn_done):
            if w in self.sel_list:
                self.del_sel_widget(w)
        for w in self._capture_group:
            w.hide(refresh=False)
        self._refresh_knob_values()
        for w in self._setup_group:
            w.show(refresh=False)
        self.add_sel_widget(self._name_btn)
        self.add_sel_widget(self._btn_setup_close)
        self.add_sel_widget(self._btn_start)
        self._in_capture_view = False
        self.refresh()

    def _update_cap_name_label(self, name: str) -> None:
        tw, _ = get_text_size(name, self._caption_font)
        rx = _W - 4 - tw
        self._cap_name_lbl.set_text(name, _HEADER_NAME_FG, x=rx)

    def _nudge_audio(self, is_gain: bool, steps: int) -> None:
        """Adjust input gain or output volume by steps encoder detents.

        Tracks the desired value internally so hardware quantization can't
        stall incremental movement — the same approach the normal encoder uses
        via its step_values array.  Step size matches the normal encoder's
        256-step float resolution (~0.124 dB/step over a 31.75 dB range).
        """
        if self._handler is None:
            return
        step_size = 31.75 / 256.0
        if is_gain:
            self._gain_val = max(-19.75, min(12.0, self._gain_val + steps * step_size))
            self._handler.audio_parameter_commit(self._handler.audiocard.CAPTURE_VOLUME, self._gain_val)
            self._knob_gain.set_value(self._gain_val)
        else:
            self._vol_val = max(-25.75, min(6.0, self._vol_val + steps * step_size))
            self._handler.audio_parameter_commit(self._handler.audiocard.MASTER, self._vol_val)
            self._knob_vol.set_value(self._vol_val)

    def _init_knob_values(self) -> None:
        """Snapshot HW levels, then apply persisted NAM levels (defaults -10 dB)."""
        if self._handler is not None:
            ac = self._handler.audiocard
            hw_gain = ac.get_volume_parameter(ac.CAPTURE_VOLUME)
            hw_vol = ac.get_volume_parameter(ac.MASTER)
            self._saved_gain = hw_gain if hw_gain != 0.0 else -10.0
            self._saved_vol = hw_vol if hw_vol != 0.0 else -10.0
            self._gain_val = self._handler.settings.get_setting(Token.NAM_CAPTURE_GAIN) or -10.0
            self._vol_val = self._handler.settings.get_setting(Token.NAM_OUTPUT_VOL) or -10.0
            self._handler.audio_parameter_commit(ac.CAPTURE_VOLUME, self._gain_val)
            self._handler.audio_parameter_commit(ac.MASTER, self._vol_val)
        self._refresh_knob_values()

    def _refresh_knob_values(self) -> None:
        """Update knob display from tracked values (no hardware read)."""
        self._knob_gain.set_value(self._gain_val)
        self._knob_vol.set_value(self._vol_val)
