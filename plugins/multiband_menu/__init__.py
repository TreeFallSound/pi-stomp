"""Reusable custom-layout menu widget for low-band-count multi-band plugins."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Sequence

import pygame

from common.parameter import Parameter
from modalapi.plugin import Plugin
from uilib.box import Box
from uilib.config import Config
from uilib.container import ContainerWidget
from uilib.glyphs.arc_ring import ArcRingGlyph
from uilib.misc import InputEvent, get_text_size
from uilib.panel import Panel
from uilib.text import Button
from uilib.widget import Widget
from pistomp.input.event import ControllerEvent, EncoderEvent

# ── layout constants ──────────────────────────────────────────────────────────

_ARC_RADIUS = 28
_ARC_MARGIN = 2


@dataclass(frozen=True)
class ParamSlot:
    """One arc-ring slot in a custom layout menu."""

    symbol: str
    label: str
    color: tuple[int, int, int]
    display_fn: Callable[[float], str] | None = None


class CustomMenuWidget(ContainerWidget):
    """2x4 arc-ring menu widget for up to 8 parameters.

    Subclasses provide the parameter slots via ``build_slots()``.  The widget
    manages selection, drawing, and tweak-encoder edits: Tweak1 adjusts the
    selected parameter, Tweak2/3 are ignored.  Selection reticules are drawn
    around each slot's bounding box.
    """

    def __init__(self, *, box: Box, plugin: Plugin, parent: "Widget", **kwargs) -> None:
        super().__init__(box=box, parent=parent, **kwargs)
        self.plugin = plugin
        self.slots = self.build_slots()
        if not self.slots:
            raise ValueError("CustomMenuWidget requires at least one ParamSlot")

        cfg = Config()
        self._value_font = cfg.get_font("small") or cfg.get_font("default")
        self._label_font = cfg.get_font("tiny") or self._value_font
        assert self._value_font is not None and self._label_font is not None

        self._ring = ArcRingGlyph(radius=_ARC_RADIUS)
        self._slot_widgets: list[_ParamSlotWidget] = []
        self._build_slots()

    # ── subclass contract ──────────────────────────────────────────────────

    def build_slots(self) -> Sequence[ParamSlot]:
        raise NotImplementedError

    # ── construction ────────────────────────────────────────────────────────

    def _build_slots(self) -> None:
        n = len(self.slots)
        # Prefer 2 rows; 1 row if <=4 slots.
        cols = 4 if n > 4 else n
        rows = (n + cols - 1) // cols

        cell_w = self.box.width // cols
        cell_h = self.box.height // rows
        ring_size = self._ring.size
        ring_w = ring_size + _ARC_MARGIN * 2
        ring_h = ring_size + _ARC_MARGIN * 2

        for i, slot in enumerate(self.slots):
            col = i % cols
            row = i // cols
            cx = col * cell_w + cell_w // 2
            cy = row * cell_h + cell_h // 2
            x0 = cx - ring_w // 2
            y0 = cy - ring_h // 2
            box = Box.xywh(x0, y0, ring_w, ring_h)
            w = _ParamSlotWidget(
                box=box,
                slot=slot,
                plugin=self.plugin,
                ring=self._ring,
                value_font=self._value_font,
                label_font=self._label_font,
                parent=self,
            )
            self._slot_widgets.append(w)
            self.add_sel_widget(w)

    # ── input dispatch ──────────────────────────────────────────────────────

    def input_event(self, event) -> bool:
        sel_ref = self.sel_ref  # type: ignore[attr-defined]
        if sel_ref is None:
            return False
        if sel_ref.input_event(event):
            return True
        if isinstance(event, EncoderEvent):
            if event.controller.id == 1 and isinstance(sel_ref, _ParamSlotWidget):
                return sel_ref.on_encoder_rotation(event.rotations)
        return False


class _ParamSlotWidget(Widget):
    """Single arc-ring + label + value slot."""

    def __init__(
        self,
        *,
        box: Box,
        slot: ParamSlot,
        plugin: Plugin,
        ring: ArcRingGlyph,
        value_font,
        label_font,
        parent: "Widget",
    ) -> None:
        super().__init__(box=box, parent=parent, visible=True)
        self.slot = slot
        self.plugin = plugin
        self._ring = ring
        self._value_font = value_font
        self._label_font = label_font
        self._value: float | None = None
        self._update_value()

    def _update_value(self) -> None:
        param = self.plugin.parameters.get(self.slot.symbol)
        self._value = param.value if param is not None else None

    def set_param(self, value: float) -> None:
        param = self.plugin.parameters.get(self.slot.symbol)
        if param is None:
            return
        self._value = value
        param.value = value
        self._send_param()
        self.refresh()

    def _send_param(self) -> None:
        # Find the top-level panel and use its handler to send the parameter.
        panel = self._get_panel()
        if panel is None:
            return
        bridge = getattr(panel, "ws_bridge", None)
        if bridge is None:
            return
        bridge.send_parameter(self.plugin.instance_id, self.slot.symbol, self._value)

    def _value_as_t(self) -> float:
        param = self.plugin.parameters.get(self.slot.symbol)
        if param is None or self._value is None:
            return 0.0
        lo = param.minimum
        hi = param.maximum
        if hi == lo:
            return 0.0
        return (self._value - lo) / (hi - lo)

    def _format_value(self) -> str:
        if self._value is None:
            return "--"
        if self.slot.display_fn is not None:
            return self.slot.display_fn(self._value)
        param = self.plugin.parameters.get(self.slot.symbol)
        if param is not None:
            return param.format(self._value)
        return f"{self._value:.1f}"

    def input_event(self, event) -> bool:
        if event == InputEvent.CLICK:
            return True
        if event == InputEvent.LONG_CLICK:
            self._reset_to_snapshot()
            return True
        return False

    def _reset_to_snapshot(self) -> None:
        snap = self.plugin.pedalboard_snapshot
        if self.slot.symbol in snap:
            self.set_param(snap[self.slot.symbol])

    def on_encoder_rotation(self, rotations: int) -> bool:
        param = self.plugin.parameters.get(self.slot.symbol)
        if param is None or self._value is None:
            return False
        step = self._compute_step(param)
        new_value = self._value + rotations * step
        new_value = max(param.minimum, min(param.maximum, new_value))
        if new_value != self._value:
            self.set_param(new_value)
            return True
        return True

    @staticmethod
    def _compute_step(param: Parameter) -> float:
        t = param.type
        if t in (Parameter.Type.ENUMERATION, Parameter.Type.INTEGER, Parameter.Type.TOGGLED):  # type: ignore[attr-defined]
            return 1.0
        span = param.maximum - param.minimum
        if t == Parameter.Type.LOGARITHMIC:  # type: ignore[attr-defined]
            # Multiplicative step: ~1/24 octave per detent
            ratio = 2.0 ** (1.0 / 12.0)
            return max(0.01, (param.value or param.minimum) * (ratio - 1.0))
        return max(0.01, span / 100.0)

    def set_selected(self, selected: bool) -> None:  # type: ignore[override]
        self.selected = selected
        self.refresh()

    def _draw_erase(self, ctx) -> None:
        ctx.draw_rectangle(ctx.bounds, fill=self.bkgnd_color)

    def _draw(self, ctx) -> None:
        t = self._value_as_t()
        ring_surf = self._ring.render(
            t,
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
        ctx.draw_text(
            ((ctx.width - tw) // 2, cy - th // 2),
            value_text,
            fill=(255, 255, 255),
            font=self._value_font,
        )

        lw, lh = get_text_size(self.slot.label, self._label_font)
        ctx.draw_text(
            ((ctx.width - lw) // 2, cy + half + 2),
            self.slot.label,
            fill=(180, 180, 180),
            font=self._label_font,
        )


# Convenience registration helper for plugins that just need this widget.
def register_menu_widget(uri: str, *, display_name: str | None = None) -> None:
    """Register a plugin whose long-press menu uses a CustomMenuWidget subclass."""
    raise NotImplementedError("Use a concrete widget subclass and PluginCustomization.menu_widget_cls")
