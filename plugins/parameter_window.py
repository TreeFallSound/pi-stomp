"""Combined parameter window: arc rings pinned up top, scrollable list below.

``ParameterWindow`` is the generalisation of ``MultibandWindow`` — it replaces
the old generic parameter menu (``draw_parameter_menu``) and the multiband arc
grid with a single ``PluginWindow`` that shows pinned params as arc rings and
the rest as a scrollable text list.

Subclasses (the old ``MultibandWindow`` subclasses) override ``build_slots()``
to supply their own pinned slots. The generic fallback reads
``plugin.customization.pinned_params`` or uses a heuristic (first N continuous
params in sorted order).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from common.contexts import (
    BindingDecl,
    ContextKind,
    ContextRef,
    ControlClass,
    ControlRef,
    EventKind,
    SelectionEditEffect,
)
from common.parameter import Parameter
from common.param_roles import ParamRole
from modalapi.plugin_customization import PinnedParam
from plugins.chrome import BTN_GAP, BTN_H, MIN_CHROME_WIDTH, build_bottom_row
from plugins.scheme import scheme_for_category
from plugins.window import PluginWindow
from uilib.box import Box
from uilib.config import Config
from uilib.container import ContainerWidget
from uilib.dialog import Dialog, DialogDecorator
from uilib.glyphs.arc_dial import ArcDialWidget, dial_box_size
from uilib.glyphs.badge import BadgeGlyph
from uilib.misc import INACTIVE_SHADE, InputEvent, color_for_param, get_text_size, shade_color, step_for_param
from uilib.widget import Widget

# ── layout constants ──────────────────────────────────────────────────────────

_ARC_RADIUS = 28
_MAX_H = 189
_MAX_PINNED = 4

_BADGE_TWEAK1 = BadgeGlyph("1")
_BADGE_GAP = 3  # matches TextWidget's badge_gap

_ROW_H = 20


def _slot_box_size() -> tuple[int, int]:
    return dial_box_size(_ARC_RADIUS, Config().get_font("arc_label"))


class ParamSlotWidget(ArcDialWidget):
    """One pinned parameter as an arc dial. The base owns the rendering; this
    adds the plugin binding — edits route through the owner window."""

    def __init__(
        self,
        *,
        box: Box,
        slot: PinnedParam,
        owner: PluginWindow,
        parent: Widget,
        badge_char: str | None = None,
    ) -> None:
        self.slot = slot
        self._owner = owner
        param = owner.plugin.parameters.get(slot.symbol)
        super().__init__(
            box=box,
            label=slot.label,
            minimum=param.minimum if param is not None else 0.0,
            maximum=param.maximum if param is not None else 1.0,
            color=color_for_param(param),
            formatter=self._format,
            parent=parent,
            radius=_ARC_RADIUS,
            two_line=False,
            label_pos="top",
        )
        if badge_char is not None:
            self.set_badge(BadgeGlyph(badge_char))
        self.sync()

    def _param(self) -> Parameter | None:
        return self._owner.plugin.parameters.get(self.slot.symbol)

    def _format(self, value: float) -> tuple[str, str]:
        param = self._param()
        if param is None:
            return ("--", "")
        if self.slot.display_fn is not None:
            return (self.slot.display_fn(value), "")
        return (param.format_value(value), param.unit_symbol or "")

    def sync(self) -> None:
        param = self._param()
        if param is not None and param.value is not None:
            self.set_value(float(param.value))

    def set_param(self, value: float) -> None:
        self.set_value(value)
        self._owner.set_param(self.slot.symbol, value)

    def input_event(self, event) -> bool:
        if event == InputEvent.LONG_CLICK:
            snap = self._owner.plugin.pedalboard_snapshot
            if self.slot.symbol in snap:
                self.set_param(snap[self.slot.symbol])
            return True
        return False

    def on_encoder_rotation(self, rotations: int) -> bool:
        param = self._param()
        if param is None:
            return False
        self.set_param(self.value + rotations * step_for_param(param))
        return True

    def symbol_for(self, role: ParamRole) -> str | None:
        return self.slot.symbol

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.refresh()
        if selected:
            self.scroll_into_view()


class _ListRow(Widget):
    """A single parameter row in the scrollable list: badge + name."""

    def __init__(
        self,
        *,
        box: Box,
        symbol: str,
        label: str,
        badge_char: str | None,
        owner: ParameterWindow,
        font,
        parent: Widget,
    ) -> None:
        super().__init__(box=box, parent=parent, visible=True)
        self.symbol = symbol
        self._label = label
        self._badge_char = badge_char
        self._owner = owner
        self._font = font
        self._bypassed: bool = False

    def set_bypassed(self, bypassed: bool) -> None:
        if bypassed == self._bypassed:
            return
        self._bypassed = bypassed
        self.refresh()

    def symbol_for(self, role: ParamRole) -> str | None:
        return self.symbol

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.refresh()
        if selected:
            self.scroll_into_view()

    def _draw_erase(self, ctx) -> None:
        ctx.draw_rectangle(ctx.bounds, fill=self.bkgnd_color)

    def _draw(self, ctx) -> None:
        shade = INACTIVE_SHADE if self._bypassed else 1.0
        fg = shade_color((255, 255, 255), shade)
        _, line_h = get_text_size("", self._font)
        vy = (ctx.height - line_h) // 2
        tw, _ = get_text_size(self._label, self._font)
        text_x = (ctx.width - tw) // 2
        ctx.draw_text((text_x, vy), self._label, font=self._font, fill=fg)
        # Badge is out of flow: pinned left of the rendered text, which stays
        # centred whether the row is badged or not.
        if self._badge_char is not None:
            badge = BadgeGlyph(self._badge_char)
            bx = max(0, text_x - _BADGE_GAP - badge.width)
            ctx.paste(badge.render(), (bx, (ctx.height - badge.height) // 2))


class _ScrollContainer(ContainerWidget):
    """A container that scrolls pixel-precise (no page-snap)."""

    def _scroll_delta(self, box, movex, movey, orig_box):
        return 0, movey


class ParameterWindow(PluginWindow[None]):
    """Windowed arc-ring + scrollable-list UI for any plugin.

    Pinned params (from ``build_slots()`` or ``pinned_params`` customization)
    render as arc rings at the top. Remaining params render as a scrollable
    text list below. The Back/Bypass/Reset chrome is inherited from
    ``PluginWindow``.
    """

    def __init__(
        self,
        *,
        plugin,
        handler,
        on_dismiss,
        badge_fn: Callable[[Parameter], str | None] | None = None,
    ) -> None:
        self._badge_fn = badge_fn
        self._init_plugin_state(plugin, handler, on_dismiss)

        w, h = self._window_size()
        w = max(w, MIN_CHROME_WIDTH)
        self._win_w, self._win_h = w, h

        cfg = Config()
        self._title_font = cfg.get_font("default_title")
        self._btn_font = cfg.get_font("small")

        scheme = scheme_for_category(plugin.category)

        Dialog.__init__(
            self, width=w, height=h, title=plugin.display_name, title_font=self._title_font, auto_destroy=True, scheme=scheme
        )

        pad = 2
        self.content_box = Box.xywh(0, pad, w, h - pad)
        self.build_widgets()
        self._refresh_bypass_style()

    # ── subclass contract ──────────────────────────────────────────────────

    def build_slots(self) -> Sequence[PinnedParam]:
        """Return pinned slots. Override in subclasses for custom pinning.

        Default: read ``pinned_params`` from customization, or heuristic
        (first up-to-4 continuous params in sorted order).
        """
        pinned = self.plugin.customization.pinned_params
        if pinned is not None:
            return pinned
        return self._heuristic_slots()

    def _heuristic_slots(self) -> list[PinnedParam]:
        """First up-to-4 continuous (non-enum, non-toggle) params."""
        slots: list[PinnedParam] = []
        for name, param in sorted(self.plugin.parameters.items()):
            if name == ":bypass":
                continue
            if param.type.value in (1, 5):  # ENUMERATION, TOGGLED
                continue
            if len(slots) >= _MAX_PINNED:
                break
            slots.append(PinnedParam(symbol=name, label=name))
        return slots

    # ── PluginWindow contract ───────────────────────────────────────────────

    def _window_size(self) -> tuple[int, int]:
        self.slots = self.build_slots()
        n = len(self.slots)
        cols = 4 if n > 4 else n
        rows = (n + cols - 1) // cols if n else 0
        _, row_h = _slot_box_size()
        ring_h = rows * row_h if rows else 0
        list_h = len(self._list_params()) * _ROW_H
        btn_h = BTN_H + BTN_GAP * 2
        content_h = ring_h + list_h + btn_h
        return (self.WIN_W, min(_MAX_H, content_h))

    def snapshot_state(self) -> None:
        return None

    def apply_state(self, state: None) -> None:
        for w in self._slot_widgets:
            w.sync()
        for w in self._list_rows:
            w.refresh()

    def _badge_for(self, symbol: str) -> str | None:
        """The physical-control badge for *symbol*, or None. Rings, list rows
        and the Bypass button all badge from here — a pinned param must not
        lose its badge just because it renders as an arc ring."""
        if self._badge_fn is None:
            return None
        param = self.plugin.parameters.get(symbol)
        return self._badge_fn(param) if param is not None else None

    def _list_params(self) -> list[tuple[str, Parameter]]:
        """Params not pinned, in sorted order, excluding :bypass."""
        pinned_symbols = {s.symbol for s in self.slots}
        result: list[tuple[str, Parameter]] = []
        for name, param in sorted(self.plugin.parameters.items()):
            if name == ":bypass":
                continue
            if name in pinned_symbols:
                continue
            result.append((name, param))
        return result

    def build_widgets(self) -> None:
        row_font = Config().get_font("default")

        self._slot_widgets: list[ParamSlotWidget] = []
        self._list_rows: list[_ListRow] = []

        cb = self.content_box
        n = len(self.slots)
        cols = 4 if n > 4 else n
        rows = (n + cols - 1) // cols if n else 0
        cell_w = cb.width // cols if cols else cb.width
        ring_wh, box_h = _slot_box_size()
        ring_area_h = rows * box_h if rows else 0
        list_params = self._list_params()
        btn_area_h = BTN_H + BTN_GAP * 2
        total_content_h = ring_area_h + len(list_params) * _ROW_H + btn_area_h
        needs_scroll = total_content_h > cb.height

        content_container = _ScrollContainer(
            box=Box.xywh(cb.x0, cb.y0, cb.width, cb.height),
            virtual=needs_scroll,
            content_height=total_content_h if needs_scroll else None,
            parent=self,
        )
        self._content_container = content_container

        for i, slot in enumerate(self.slots):
            col = i % cols
            row = i // cols
            cx = col * cell_w + cell_w // 2
            cy = row * box_h + box_h // 2
            box = Box.xywh(cx - ring_wh // 2, cy - box_h // 2, ring_wh, box_h)
            w = ParamSlotWidget(
                box=box,
                slot=slot,
                owner=self,
                badge_char=self._badge_for(slot.symbol),
                parent=content_container,
            )
            self._slot_widgets.append(w)
            content_container.add_sel_widget(w)

        for idx, (name, _param) in enumerate(list_params):
            y = ring_area_h + idx * _ROW_H
            row = _ListRow(
                box=Box.xywh(0, y, cb.width, _ROW_H),
                symbol=name,
                label=name,
                badge_char=self._badge_for(name),
                owner=self,
                font=row_font,
                parent=content_container,
            )
            self._list_rows.append(row)
            content_container.add_sel_widget(row)

        # The button row is the last thing in the scrolling body, not fixed
        # chrome — same as a Menu's trailing back arrow.
        btn_y = ring_area_h + len(list_params) * _ROW_H + BTN_GAP
        _, btn_text_h = get_text_size("Bypass", self._btn_font)
        btn_v_margin = max(0, (BTN_H - btn_text_h) // 2)
        self._btn_back, self._btn_bypass, self._btn_reset = build_bottom_row(
            parent=content_container,
            width=cb.width,
            bottom_y=btn_y,
            font=self._btn_font,
            v_margin=btn_v_margin,
            on_back=lambda *_: self._on_dismiss(),
            on_bypass=lambda *_: self._on_toggle_bypass(),
            on_reset=lambda *_: self._on_reset(),
        )
        for btn in (self._btn_back, self._btn_bypass, self._btn_reset):
            content_container.add_sel_widget(btn)

        bypass_badge = self._badge_for(":bypass")
        if bypass_badge is not None:
            self._btn_bypass.set_badge(BadgeGlyph(bypass_badge))

        content_container.refresh()
        self.add_sel_widget(content_container)

        deco = self.decorator
        assert isinstance(deco, DialogDecorator), "ParameterWindow is always Dialog-decorated"
        deco.title.set_badge(_BADGE_TWEAK1)

    def declare_bindings(self) -> tuple[BindingDecl, ...]:
        return (
            BindingDecl(
                control=ControlRef(cls=ControlClass.TWEAK, id=1),
                event_kind=EventKind.ROTATE,
                effects=(SelectionEditEffect(),),
                context=ContextRef(kind=ContextKind.PANEL, name="parameter_window"),
            ),
        )

    def edit_symbol(self, symbol: str, rotations: int) -> bool:
        widget = next((w for w in self._slot_widgets if w.slot.symbol == symbol), None)
        if widget is not None:
            return widget.on_encoder_rotation(rotations)
        return super().edit_symbol(symbol, rotations)

    def _on_toggle_bypass(self) -> None:
        super()._on_toggle_bypass()
        bypassed = self.plugin.is_bypassed()
        for w in self._slot_widgets:
            w.set_bypassed(bypassed)
        for w in self._list_rows:
            w.set_bypassed(bypassed)

    def _refresh_bypass_style(self) -> None:
        super()._refresh_bypass_style()
        bypassed = self.plugin.is_bypassed()
        for w in self._slot_widgets:
            w.set_bypassed(bypassed)
        for w in self._list_rows:
            w.set_bypassed(bypassed)
