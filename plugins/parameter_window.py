"""Combined parameter window: arc rings pinned up top, scrollable list below.

The one window for any plugin without a bespoke panel. Pinned params render as
arc rings, the rest as a scrollable text list. Pinning is declared, not coded —
``PluginCustomization.pinned_params``; with none declared a heuristic pins the
first few continuous params.

Ports the plugin exposes but no UI should paint (``Plugin.visible_parameters``)
never appear in either.
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
from common.parameter import BYPASS_SYMBOL, Parameter, Symbol, Type
from common.parameter_steps import ParameterSteps
from common.param_roles import ParamRole
from modalapi.plugin_customization import PinnedParam
from plugins.chrome import BTN_GAP, BTN_H, MIN_CHROME_WIDTH, build_bottom_row
from plugins.eq.parametric import paint_band_node
from plugins.scheme import scheme_for_category
from plugins.window import PluginWindow
from uilib.box import Box
from uilib.config import Config
from uilib.container import ContainerWidget
from uilib.dialog import Dialog, DialogDecorator
from uilib.glyphs.arc_dial import ArcDialWidget, dial_box_size
from uilib.glyphs.badge import BadgeGlyph
from uilib.glyphs.bar import READOUT_COLOR, TRACK_COLOR, paint_bar
from uilib.misc import INACTIVE_SHADE, InputEvent, color_for_param, get_text_size, shade_color
from uilib.widget import Widget

# ── layout constants ──────────────────────────────────────────────────────────

_ARC_RADIUS = 28
_MAX_H = 189
_MAX_PINNED = 4
# Below this the Back/Bypass/Reset labels start to clip; a window with fewer than
# _MAX_PINNED rings narrows to its ring row but never past this floor.
_MIN_WINDOW_W = 240

_BADGE_TWEAK1 = BadgeGlyph("1")

_ROW_H = 24
_NAME_MARGIN = 4
_NAME_BADGE_GAP = 2  # between the left-column badge and the name text
_RIGHT_MARGIN = 4
_BAR_LEN = 72
_BAR_THICK = 3  # matches graphic EQ BAR_W / node diameter
_VALUE_GAP = 5  # between bar and value readout
_VALUE_W = 42  # fixed value-column width so the bar's right edge doesn't jump

_EMPTY_LABEL = "No editable parameters"


def _fit_text(text: str, font, max_w: int) -> str:
    """Trim from the end until *text* fits in *max_w* px — enum labels can be
    wider than the fixed value column; a clip keeps the bar edge put."""
    while text and get_text_size(text, font)[0] > max_w:
        text = text[:-1]
    return text


def _slot_box_size() -> tuple[int, int]:
    return dial_box_size(_ARC_RADIUS, Config().get_font("arc_label"))


def _discrete_formatter(param: Parameter) -> Callable[[float], tuple[str, str]] | None:
    """A discrete param's ring shows its picked label, not the raw port value:
    an ordered enum's scale-point label (Order 0/1/2 → "1"/"2"/"3") or a
    toggle's On/Off. Continuous params keep the default."""
    if param.type == Type.TOGGLED:
        midpoint = (param.minimum + param.maximum) / 2

        def fmt_toggle(value: float) -> tuple[str, str]:
            return ("On" if value >= midpoint else "Off", "")

        return fmt_toggle
    if not param.is_ordered_enum():
        return None
    pairs = param.get_enum_value_list()

    def fmt(value: float) -> tuple[str, str]:
        idx = min(range(len(pairs)), key=lambda i: abs(pairs[i][1] - value))
        return (pairs[idx][0], "")

    return fmt


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
            two_line=True,
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
            return self.slot.display_fn(value)
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

    def on_encoder_rotation(self, rotations: int, multiplier: float = 1.0) -> bool:
        param = self._param()
        if param is None:
            return False
        steps = ParameterSteps.for_parameter(param)
        delta = int(round(rotations * multiplier))
        if delta == 0:
            return False
        new_val = steps.move(delta)
        if new_val == self.value:
            return False
        self.set_param(new_val)
        return True

    def symbol_for(self, role: ParamRole) -> Symbol | None:
        return self.slot.symbol

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.refresh()
        if selected:
            self.scroll_into_view()


class _ListRow(Widget):
    """A live parameter row: left-aligned name, then a right-aligned block of
    badge + horizontal EQ-style bar + value readout. Tweak1-reactive on the
    selected row; the brighter fill + node halo is its selection cue."""

    def __init__(
        self,
        *,
        box: Box,
        symbol: Symbol,
        label: str,
        badge_char: str | None,
        owner: ParameterWindow,
        font,
        value_font,
        parent: Widget,
    ) -> None:
        super().__init__(box=box, parent=parent, visible=True)
        self.symbol = symbol
        self._label = label
        self._badge_char = badge_char
        self._owner = owner
        self._font = font
        self._value_font = value_font
        self._bypassed: bool = False

    def _param(self) -> Parameter | None:
        return self._owner.plugin.parameters.get(self.symbol)

    @staticmethod
    def _is_discrete(param: Parameter) -> bool:
        """Enums and toggles read as a picked label, not a level — no bar."""
        return param.type in (Type.ENUMERATION, Type.TOGGLED)

    @staticmethod
    def _discrete_label(param: Parameter, value: float) -> str:
        """The chosen enum scale-point label, or On/Off for a toggle."""
        if param.type == Type.ENUMERATION:
            pairs = param.get_enum_value_list()
            if pairs:
                idx = min(range(len(pairs)), key=lambda i: abs(pairs[i][1] - value))
                return pairs[idx][0]
            return "%d" % round(value)
        on = value >= (param.minimum + param.maximum) / 2
        return "On" if on else "Off"

    @staticmethod
    def _continuous_readout(param: Parameter, value: float) -> tuple[str, float]:
        """(text, 0..1 fill fraction) for a level-style param: compact numeric
        (≤1 decimal, no space before the unit) filling over min..max."""
        if param.type == Type.INTEGER:
            num = "%d" % round(value)
        else:
            num = f"{value:.1f}".rstrip("0").rstrip(".")
        span = param.maximum - param.minimum
        frac = 0.0 if span <= 0 else (value - param.minimum) / span
        return f"{num}{param.unit_symbol or ''}", frac

    def set_bypassed(self, bypassed: bool) -> None:
        if bypassed == self._bypassed:
            return
        self._bypassed = bypassed
        self.refresh()

    def symbol_for(self, role: ParamRole) -> Symbol | None:
        return self.symbol

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.refresh()
        if selected:
            self.scroll_into_view()

    def on_encoder_rotation(self, rotations: int, multiplier: float = 1.0) -> bool:
        param = self._param()
        if param is None:
            return False
        steps = ParameterSteps.for_parameter(param)
        delta = int(round(rotations * multiplier))
        if delta == 0:
            return False
        new_val = steps.move(delta)
        if new_val == param.value:
            return False
        self._owner.set_param(self.symbol, new_val)
        self.refresh()
        return True

    def _draw_erase(self, ctx) -> None:
        ctx.draw_rectangle(ctx.bounds, fill=self.bkgnd_color)

    def _draw(self, ctx) -> None:
        shade = INACTIVE_SHADE if self._bypassed else 1.0
        fg = shade_color((255, 255, 255), shade)
        _, line_h = get_text_size("", self._font)
        vy = (ctx.height - line_h) // 2

        param = self._param()

        # Right block: bar+value for level params, a picked label for enum/toggle.
        if param is not None and param.value is not None:
            if self._is_discrete(param):
                self._draw_label(ctx, param, float(param.value), shade)
            else:
                self._draw_bar(ctx, param, float(param.value), shade)

        # Left column: the name, then its badge (nudged 1px low) just to its right.
        ctx.draw_text((_NAME_MARGIN, vy), self._label, font=self._font, fill=fg)
        if self._badge_char is not None:
            badge = BadgeGlyph(self._badge_char)
            tw, _ = get_text_size(self._label, self._font)
            bx = _NAME_MARGIN + tw + _NAME_BADGE_GAP
            ctx.paste(badge.render(), (bx, (ctx.height - badge.height) // 2))

    def _draw_label(self, ctx, param: Parameter, value: float, shade: float) -> None:
        """Enum/toggle: right-aligned picked label, no bar."""
        label = _fit_text(self._discrete_label(param, value), self._value_font, _BAR_LEN + _VALUE_GAP + _VALUE_W)
        _, val_h = get_text_size("", self._value_font)
        val_vy = (ctx.height - val_h) // 2
        lw, _ = get_text_size(label, self._value_font)
        lx = ctx.width - _RIGHT_MARGIN - lw
        # An engaged toggle lifts its label out of the muted readout grey.
        on = param.type == Type.TOGGLED and value >= (param.minimum + param.maximum) / 2
        color = (255, 255, 255) if on else READOUT_COLOR
        ctx.draw_text((lx, val_vy), label, font=self._value_font, fill=shade_color(color, shade))

    def _draw_bar(self, ctx, param: Parameter, value: float, shade: float) -> None:
        """Level-style param: horizontal bar + right-aligned readout. The value's
        right edge is pinned so it stays put and, when too wide for its column,
        spills left over the bar (drawn last, on top); the fill takes the same
        colour the param would get as a pinned arc ring."""
        value_str, frac = self._continuous_readout(param, value)
        bar_x0 = ctx.width - _RIGHT_MARGIN - _VALUE_W - _VALUE_GAP - _BAR_LEN

        ring_color = color_for_param(param)
        fill_color = ring_color if self.selected else shade_color(ring_color, 0.55)
        if shade < 1.0:
            fill_color = shade_color(fill_color, shade)
        node_x, node_y = paint_bar(
            ctx,
            box=Box(bar_x0, 0, bar_x0 + _BAR_LEN, ctx.height),
            orientation="horizontal",
            frac=frac,
            track_color=TRACK_COLOR,
            fill_color=fill_color,
            thickness=_BAR_THICK,
        )
        node_color = shade_color(ring_color, shade) if shade < 1.0 else ring_color
        paint_band_node(ctx, node_x, node_y, node_color, self.selected)

        _, val_h = get_text_size("", self._value_font)
        val_vy = (ctx.height - val_h) // 2
        vw, _ = get_text_size(value_str, self._value_font)
        ctx.draw_text(
            (ctx.width - _RIGHT_MARGIN - vw, val_vy),
            value_str,
            font=self._value_font,
            fill=shade_color(READOUT_COLOR, shade),
        )


class _EmptyRow(Widget):
    """Placeholder when every port is pinned, bypass, or hidden. Never added to
    the container's sel-widget list — there is nothing here to select."""

    def __init__(self, *, box: Box, font, parent: Widget) -> None:
        super().__init__(box=box, parent=parent, visible=True)
        self._font = font

    def _draw_erase(self, ctx) -> None:
        ctx.draw_rectangle(ctx.bounds, fill=self.bkgnd_color)

    def _draw(self, ctx) -> None:
        fg = shade_color((255, 255, 255), INACTIVE_SHADE)
        tw, line_h = get_text_size(_EMPTY_LABEL, self._font)
        ctx.draw_text(((ctx.width - tw) // 2, (ctx.height - line_h) // 2), _EMPTY_LABEL, font=self._font, fill=fg)


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
            self,
            width=w,
            height=h,
            title=plugin.display_name,
            title_font=self._title_font,
            auto_destroy=True,
            scheme=scheme,
        )

        pad = 2
        self.content_box = Box.xywh(0, pad, w, h - pad)
        self.build_widgets()
        self._refresh_bypass_style()
        self._start_observing()

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
        """First up-to-4 params that read as a dial: continuous, a toggle
        (On/Off), or an ordered integer enum (Filter Order, Compressor Mode)."""
        slots: list[PinnedParam] = []
        for name, param in sorted(self.plugin.visible_parameters.items()):
            if name == BYPASS_SYMBOL:
                continue
            if param.type == Type.ENUMERATION and not param.is_ordered_enum():
                continue
            if len(slots) >= _MAX_PINNED:
                break
            slots.append(PinnedParam(symbol=name, label=name, display_fn=_discrete_formatter(param)))
        return slots

    # ── PluginWindow contract ───────────────────────────────────────────────

    def _is_empty(self) -> bool:
        """Every port pinned, bypass, or hidden — nothing left to list or select."""
        return not self.slots and not self._list_params()

    def _window_size(self) -> tuple[int, int]:
        self.slots = self.build_slots()
        n = len(self.slots)
        cols = 4 if n > 4 else n
        rows = (n + cols - 1) // cols if n else 0
        ring_wh, row_h = _slot_box_size()
        ring_h = rows * row_h if rows else 0
        list_h = _ROW_H if self._is_empty() else len(self._list_params()) * _ROW_H
        btn_h = BTN_H + BTN_GAP * 2
        content_h = ring_h + list_h + btn_h
        if n >= _MAX_PINNED:
            w = self.WIN_W
        else:
            w = max(_MIN_WINDOW_W, min(self.WIN_W, cols * ring_wh))
        return (w, min(_MAX_H, content_h))

    def snapshot_state(self) -> None:
        return None

    def apply_state(self, state: None) -> None:
        for w in self._slot_widgets:
            w.sync()
        for w in self._list_rows:
            w.refresh()

    def _badge_for(self, symbol: Symbol) -> str | None:
        """The physical-control badge for *symbol*, or None. Rings, list rows
        and the Bypass button all badge from here — a pinned param must not
        lose its badge just because it renders as an arc ring."""
        if self._badge_fn is None:
            return None
        param = self.plugin.parameters.get(symbol)
        return self._badge_fn(param) if param is not None else None

    def _list_params(self) -> list[tuple[Symbol, Parameter]]:
        """Params not pinned, in sorted order, excluding :bypass and hidden ports."""
        pinned_symbols = {s.symbol for s in self.slots}
        result: list[tuple[Symbol, Parameter]] = []
        for name, param in sorted(self.plugin.visible_parameters.items()):
            if name == BYPASS_SYMBOL:
                continue
            if name in pinned_symbols:
                continue
            result.append((name, param))
        return result

    def build_widgets(self) -> None:
        cfg = Config()
        row_font = cfg.get_font("default")
        value_font = cfg.get_font("small")

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
        is_empty = self._is_empty()
        list_area_h = _ROW_H if is_empty else len(list_params) * _ROW_H
        btn_area_h = BTN_H + BTN_GAP * 2
        total_content_h = ring_area_h + list_area_h + btn_area_h
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
                value_font=value_font,
                parent=content_container,
            )
            self._list_rows.append(row)
            content_container.add_sel_widget(row)

        if is_empty:
            _EmptyRow(box=Box.xywh(0, ring_area_h, cb.width, _ROW_H), font=row_font, parent=content_container)

        # The button row is the last thing in the scrolling body, not fixed
        # chrome — same as a Menu's trailing back arrow.
        btn_y = ring_area_h + list_area_h + BTN_GAP
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

        bypass_badge = self._badge_for(BYPASS_SYMBOL)
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

    def edit_symbol(self, symbol: Symbol, rotations: int, multiplier: float = 1.0) -> bool:
        widget = next((w for w in self._slot_widgets if w.slot.symbol == symbol), None)
        if widget is not None:
            return widget.on_encoder_rotation(rotations, multiplier)
        row = next((r for r in self._list_rows if r.symbol == symbol), None)
        if row is not None:
            return row.on_encoder_rotation(rotations, multiplier)
        return super().edit_symbol(symbol, rotations, multiplier)

    def _refresh_bypass_style(self) -> None:
        super()._refresh_bypass_style()
        bypassed = self.plugin.is_bypassed()
        for w in self._slot_widgets:
            w.set_bypassed(bypassed)
        for w in self._list_rows:
            w.set_bypassed(bypassed)
