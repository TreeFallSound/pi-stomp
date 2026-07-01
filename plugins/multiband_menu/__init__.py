"""Reusable arc-ring grid window for low-band-count multi-band plugins.

``MultibandWindow`` is a ``PluginWindow`` whose content area is a grid of arc
rings, one per ``ParamSlot``. Subclasses just implement ``build_slots()``. Nav
cycles the rings (plus the window chrome); Tweak1 edits the selected ring.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from common.parameter import Parameter, Type
from plugins.window import PluginWindow
from uilib.box import Box
from uilib.config import Config
from uilib.glyphs.arc_ring import ArcRingGlyph
from uilib.misc import InputEvent, get_text_size
from uilib.widget import Widget

# ── layout constants ──────────────────────────────────────────────────────────

_ARC_RADIUS = 28
_ARC_MARGIN = 2
_ROW_H = 70  # vertical space one arc-ring row (ring + label) wants
_MAX_H = 236  # never exceed the 240px LCD (2px breathing room)


@dataclass(frozen=True)
class ParamSlot:
    """One arc-ring slot in a multi-band window."""

    symbol: str
    label: str
    color: tuple[int, int, int]
    display_fn: Callable[[float], str] | None = None


class MultibandWindow(PluginWindow[None]):
    """Windowed arc-ring grid for up to ~10 parameters.

    Subclasses provide the parameter slots via ``build_slots()``. The window
    manages selection (Nav), drawing, and Tweak1 edits of the selected ring.
    """

    # ── subclass contract ──────────────────────────────────────────────────

    def build_slots(self) -> Sequence[ParamSlot]:
        raise NotImplementedError

    # ── PluginWindow contract ───────────────────────────────────────────────

    def _window_size(self) -> tuple[int, int]:
        # Height tracks the row count so a 4-slot menu is a short card and only
        # the 10-band one grows toward full height.
        self.slots = self.build_slots()
        if not self.slots:
            raise ValueError("MultibandWindow requires at least one ParamSlot")
        n = len(self.slots)
        cols = 4 if n > 4 else n
        rows = (n + cols - 1) // cols
        top, bottom = self._chrome_overhead()
        return (self.WIN_W, min(_MAX_H, top + rows * _ROW_H + bottom))

    def snapshot_state(self) -> None:
        return None

    def apply_state(self, state: None) -> None:
        for w in self._slot_widgets:
            w.sync()

    def build_widgets(self) -> None:
        cfg = Config()
        value_font = cfg.get_font("small") or cfg.get_font("default")
        label_font = cfg.get_font("tiny") or value_font
        assert value_font is not None and label_font is not None

        self._ring = ArcRingGlyph(radius=_ARC_RADIUS)
        self._slot_widgets: list[_ParamSlotWidget] = []

        cb = self.content_box
        n = len(self.slots)
        cols = 4 if n > 4 else n
        rows = (n + cols - 1) // cols
        cell_w = cb.width // cols
        cell_h = cb.height // rows
        ring_wh = self._ring.size + _ARC_MARGIN * 2

        for i, slot in enumerate(self.slots):
            col = i % cols
            row = i // cols
            cx = cb.x0 + col * cell_w + cell_w // 2
            cy = cb.y0 + row * cell_h + cell_h // 2
            box = Box.xywh(cx - ring_wh // 2, cy - ring_wh // 2, ring_wh, ring_wh)
            w = _ParamSlotWidget(
                box=box,
                slot=slot,
                owner=self,
                ring=self._ring,
                value_font=value_font,
                label_font=label_font,
                parent=self,
            )
            self._slot_widgets.append(w)
            self.add_sel_widget(w)

    def on_encoder_rotation(self, encoder_id: int, rotations: int) -> bool:
        if encoder_id == 1 and isinstance(self.sel_ref, _ParamSlotWidget):
            return self.sel_ref.on_encoder_rotation(rotations)
        return False


class _ParamSlotWidget(Widget):
    """Single arc-ring + label + value slot. Edits route through the owner window."""

    def __init__(
        self,
        *,
        box: Box,
        slot: ParamSlot,
        owner: MultibandWindow,
        ring: ArcRingGlyph,
        value_font,
        label_font,
        parent: "Widget",
    ) -> None:
        super().__init__(box=box, parent=parent, visible=True)
        self.slot = slot
        self._owner = owner
        self._ring = ring
        self._value_font = value_font
        self._label_font = label_font
        self._value: float | None = None
        self.sync()

    def _param(self) -> Parameter | None:
        return self._owner.plugin.parameters.get(self.slot.symbol)

    def sync(self) -> None:
        param = self._param()
        self._value = param.value if param is not None else None
        self.refresh()

    def set_param(self, value: float) -> None:
        self._value = value
        self._owner.set_param(self.slot.symbol, value)
        self.refresh()

    def _value_as_t(self) -> float:
        param = self._param()
        if param is None or self._value is None:
            return 0.0
        lo, hi = param.minimum, param.maximum
        if hi == lo:
            return 0.0
        return (self._value - lo) / (hi - lo)

    def _format_value(self) -> str:
        if self._value is None:
            return "--"
        if self.slot.display_fn is not None:
            return self.slot.display_fn(self._value)
        param = self._param()
        if param is not None:
            return param.format(self._value)
        return f"{self._value:.1f}"

    def input_event(self, event) -> bool:
        if event == InputEvent.CLICK:
            return True
        if event == InputEvent.LONG_CLICK:
            snap = self._owner.plugin.pedalboard_snapshot
            if self.slot.symbol in snap:
                self.set_param(snap[self.slot.symbol])
            return True
        return False

    def on_encoder_rotation(self, rotations: int) -> bool:
        param = self._param()
        if param is None or self._value is None:
            return False
        new_value = self._value + rotations * self._compute_step(param)
        new_value = max(param.minimum, min(param.maximum, new_value))
        if new_value != self._value:
            self.set_param(new_value)
        return True

    @staticmethod
    def _compute_step(param: Parameter) -> float:
        t = param.type
        if t in (Type.ENUMERATION, Type.INTEGER, Type.TOGGLED):
            return 1.0
        if t == Type.LOGARITHMIC:
            # Multiplicative step: ~1/12 octave per detent.
            ratio = 2.0 ** (1.0 / 12.0)
            return max(0.01, (param.value or param.minimum) * (ratio - 1.0))
        return max(0.01, (param.maximum - param.minimum) / 100.0)

    def set_selected(self, selected: bool) -> None:  # type: ignore[override]
        self.selected = selected
        self.refresh()

    def _draw_erase(self, ctx) -> None:
        ctx.draw_rectangle(ctx.bounds, fill=self.bkgnd_color)

    def _draw(self, ctx) -> None:
        ring_surf = self._ring.render(
            self._value_as_t(),
            filled_color=self.slot.color,
            empty_color=(60, 60, 60),
            tip_color=(255, 255, 255),
        )
        half = self._ring.half_size
        cx = ctx.width // 2
        cy = ctx.height // 2
        ctx.paste(ring_surf, (cx - half, cy - half))

        value_text = self._format_value()
        tw, th = get_text_size(value_text, self._value_font)
        ctx.draw_text(((ctx.width - tw) // 2, cy - th // 2), value_text, fill=(255, 255, 255), font=self._value_font)

        lw, _ = get_text_size(self.slot.label, self._label_font)
        ctx.draw_text(((ctx.width - lw) // 2, cy + half + 2), self.slot.label, fill=(180, 180, 180), font=self._label_font)
