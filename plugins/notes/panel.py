"""Full-screen text viewer for the Notes LV2 plugin."""

from __future__ import annotations

import re
from dataclasses import dataclass

from typing_extensions import override

import common.token as Token
from modalapi.plugin import Plugin
from modalapi.plugin_customization import PluginExtraData, extra_data_as
from plugins.fullscreen import FullscreenPluginPanel
from plugins.customization import PluginCustomization, register
from plugins.notes import NOTES_URI
from pistomp.input.event import ControllerEvent, EncoderEvent
from uilib.box import Box
from uilib.config import Config
from uilib.misc import TextHAlign, get_text_size
from uilib.paint import PaintContext
from uilib.text import TextWidget
from uilib.widget import Widget

_NOTES_RE = re.compile(r'<[^>]*notes#text>\s+"""(.*?)"""', re.DOTALL)


@dataclass(frozen=True)
class NotesData(PluginExtraData):
    """The note text embedded in a Notes instance's effect TTL."""

    text: str


def _parse_notes(ttl: str) -> NotesData | None:
    m = _NOTES_RE.search(ttl)
    return NotesData(text=m.group(1)) if m else None


def _notes_text(plugin: Plugin) -> str:
    data = extra_data_as(plugin, NotesData)
    return data.text if data is not None else ""


# layout constants (shared with base)
_W = 320
_H = 240
_BTN_GAP = 2
_BTN_H = 28
_CONTENT_H = _H - _BTN_H - _BTN_GAP  # area above chrome row
_MARGIN = 4
_SB_W = 4  # scrollbar width
_SB_COLOR = (160, 160, 160)


class _ScrollbarWidget(Widget):
    """Minimal 4-px-wide scrollbar thumb. Invisible when content fits."""

    def __init__(self, box: Box, *, total: int, visible: int, **kwargs) -> None:
        self._total = total
        self._visible = visible
        self._top = 0
        super().__init__(box, **kwargs)

    def update(self, top: int) -> None:
        self._top = top
        self.refresh()

    @override
    def _draw(self, ctx: PaintContext) -> None:
        if self._total <= self._visible:
            return
        max_top = self._total - self._visible
        track_h = ctx.height
        thumb_h = max(8, track_h * self._visible // self._total)
        thumb_y = (track_h - thumb_h) * self._top // max_top if max_top > 0 else 0
        ctx.draw_rectangle(
            Box.xywh(0, thumb_y, ctx.width, thumb_h),
            fill=_SB_COLOR,
            radius=2,
        )


def _wrap_lines(text: str, font, max_w: int) -> list[str]:
    """Word-wrap `text` to fit within `max_w` pixels, preserving blank lines."""
    out: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            out.append("")
            continue
        words = stripped.split()
        buf = ""
        for word in words:
            candidate = (buf + " " + word).lstrip() if buf else word
            w, _ = get_text_size(candidate, font)
            if w <= max_w:
                buf = candidate
            else:
                if buf:
                    out.append(buf)
                buf = word
        if buf:
            out.append(buf)
    return out


class NotesPanel(FullscreenPluginPanel[None]):
    """Read-only text viewer for Notes plugin instances.

    Nav encoder scrolls line by line; all other encoder and footswitch
    events fall through to the normal handler cascade.
    """

    # ── PluginPanel contract ───────────────────────────────────────────────

    def snapshot_state(self) -> None:
        return None

    def apply_state(self, state: None) -> None:  # noqa: ARG002
        pass

    def build_widgets(self) -> None:
        cfg = Config()
        font = cfg.get_font("small") or cfg.get_font("default")
        assert font is not None

        _, line_h = get_text_size("", font)
        self._line_h = max(1, line_h)
        self._vis_count = max(1, (_CONTENT_H - _MARGIN) // self._line_h)

        raw = _notes_text(self.plugin)
        text_w = _W - 2 * _MARGIN - _SB_W - 2
        self._lines = _wrap_lines(raw, font, text_w)
        self._top = 0

        self._text_widget = TextWidget(
            box=Box.xywh(_MARGIN, _MARGIN, text_w, _CONTENT_H - _MARGIN),
            text=self._visible_text(),
            font=font,
            parent=self,
            text_halign=TextHAlign.LEFT,
            h_margin=0,
            v_margin=0,
        )
        self._scrollbar = _ScrollbarWidget(
            box=Box.xywh(_W - _SB_W - 2, _MARGIN, _SB_W, _CONTENT_H - 2 * _MARGIN),
            total=len(self._lines),
            visible=self._vis_count,
            parent=self,
        )

        # Bypass and Reset don't apply to a read-only notes viewer.
        # Hide them before base adds chrome to sel_list.
        self._btn_bypass.visible = False
        self._btn_reset.visible = False
        # Expand Back to span the full chrome row.
        self._btn_back.box = Box.xywh(_BTN_GAP, _H - _BTN_H - _BTN_GAP, _W - 2 * _BTN_GAP, _BTN_H)

    # ── encoder routing ────────────────────────────────────────────────────

    @override
    def on_encoder_rotation(self, encoder_id: int, rotations: int) -> bool:  # noqa: ARG002
        return False  # Tweak encoders fall through

    @override
    def handle(self, event: ControllerEvent) -> bool:
        if isinstance(event, EncoderEvent) and event.controller.type == Token.NAV:
            self._scroll(event.rotations)
            return True
        return super().handle(event)

    # ── internal ───────────────────────────────────────────────────────────

    def _visible_text(self) -> str:
        return "\n".join(self._lines[self._top : self._top + self._vis_count])

    def _scroll(self, delta: int) -> None:
        max_top = max(0, len(self._lines) - self._vis_count)
        new_top = max(0, min(max_top, self._top + delta))
        if new_top != self._top:
            self._top = new_top
            self._text_widget.set_text(self._visible_text())
            self._scrollbar.update(self._top)


def _notes_shortname(plugin: Plugin) -> str | None:
    text = _notes_text(plugin)
    if text:
        return "✎" + text.split("\n")[0].strip()
    return None


register(
    NOTES_URI,
    customization=PluginCustomization(
        panel_cls=NotesPanel,
        intercept_shortpress=True,
        display_name_fn=_notes_shortname,
        tile_active_color=(214, 217, 111),
    ),
    extra_data_fn=_parse_notes,
)
