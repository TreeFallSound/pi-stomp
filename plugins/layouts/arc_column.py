from __future__ import annotations

from common.parameter import Parameter
from plugins.layouts.compressor_spec import ArcSpec, arc_centers_for
from uilib.box import Box
from uilib.glyphs.arc_ring import ArcRingGlyph
from uilib.misc import INACTIVE_SHADE, get_text_size, shade_color
from uilib.widget import Widget

_ARC_RADIUS = 27
_ARC_RING_HALF = 3.0
_ARC_TIP = 3.0

_BG = (0, 0, 0)
_TEXT = (200, 224, 206)
_LABEL = (150, 168, 156)
_RETICULE = (255, 200, 90)
_RETICULE_DIM = (150, 118, 58)


class ArcSelectable(Widget):
    def __init__(self, panel, index: int, symbol: str) -> None:
        super().__init__(box=Box.xywh(0, 0, 1, 1), parent=panel, visible=True)
        self._panel = panel
        self.index = index
        self.symbol = symbol

    def set_selected(self, selected: bool) -> None:
        self.selected = selected

    def input_event(self, event) -> bool:
        from uilib.misc import InputEvent
        if event == InputEvent.LONG_CLICK:
            self._panel._reset_symbol(self.symbol)
            return True
        if event == InputEvent.CLICK:
            return True
        return False

    def scroll_into_view(self) -> bool:
        return False

    def _draw(self, ctx) -> None:
        pass

    def _draw_erase(self, ctx) -> None:
        pass

    def _draw_selection(self, ctx) -> None:
        pass


class ArcColumnWidget(Widget):
    def __init__(
        self, *, box: Box, owner, arcs: tuple[ArcSpec, ...], value_font, label_font, parent: Widget
    ) -> None:
        super().__init__(box=box, bkgnd_color=_BG, parent=parent, visible=True)
        self._owner = owner
        self._arcs = arcs
        self._centers = arc_centers_for(len(arcs))
        self._value_font = value_font
        self._label_font = label_font
        self._ring = ArcRingGlyph(_ARC_RADIUS, ring_half=_ARC_RING_HALF, tip_radius=_ARC_TIP)
        self._selected: int | None = None
        self._bypassed = False
        self._values: list[float | None] = [None] * len(arcs)
        self.sync()

    def _param(self, symbol: str) -> Parameter | None:
        return self._owner.plugin.parameters.get(symbol)

    def sync(self) -> None:
        for i, spec in enumerate(self._arcs):
            p = self._param(spec.symbol)
            self._values[i] = p.value if p is not None else None
        self.refresh()

    def sync_symbol(self, symbol: str) -> None:
        for i, spec in enumerate(self._arcs):
            if spec.symbol == symbol:
                p = self._param(symbol)
                self._values[i] = p.value if p is not None else None
                self._refresh_cell(i)
                return

    def set_active_arc(self, index: int | None) -> None:
        if index == self._selected:
            return
        old = self._selected
        self._selected = index
        for i in (old, index):
            if i is not None:
                self._refresh_cell(i)

    def set_bypassed(self, bypassed: bool) -> None:
        if bypassed == self._bypassed:
            return
        self._bypassed = bypassed
        self.refresh()

    def _refresh_cell(self, index: int) -> None:
        cx, cy = self._centers[index]
        r = _ARC_RADIUS + 12
        bx = self.box
        assert bx is not None
        self.refresh(Box(bx.x0 + cx - r, bx.y0 + cy - r, bx.x0 + cx + r, bx.y0 + cy + r + 12))

    def _value_t(self, index: int) -> float:
        p = self._param(self._arcs[index].symbol)
        v = self._values[index]
        if p is None or v is None or p.maximum == p.minimum:
            return 0.0
        return max(0.0, min(1.0, (v - p.minimum) / (p.maximum - p.minimum)))

    def _format(self, index: int) -> str:
        v = self._values[index]
        if v is None:
            return "--"
        return self._arcs[index].display_fn(v)

    def _draw(self, ctx) -> None:
        shade = INACTIVE_SHADE if self._bypassed else 1.0
        half = self._ring.half_size
        for i, spec in enumerate(self._arcs):
            cx, cy = self._centers[i]
            ring = self._ring.render(
                self._value_t(i),
                filled_color=shade_color(spec.color, shade),
                empty_color=shade_color((56, 56, 56), shade),
                tip_color=shade_color((255, 255, 255), shade),
            )
            ctx.paste(ring, (cx - half, cy - half))

            val = self._format(i)
            vw, vh = get_text_size(val, self._value_font)
            ctx.draw_text((cx - vw // 2, cy - vh // 2), val, fill=shade_color(_TEXT, shade), font=self._value_font)

            lw, _lh = get_text_size(spec.label, self._label_font)
            ctx.draw_text((cx - lw // 2, cy + half - 1), spec.label, fill=shade_color(_LABEL, shade), font=self._label_font)

            if i == self._selected:
                self._draw_reticule(ctx, cx, cy, _RETICULE if not self._bypassed else _RETICULE_DIM)

    def _draw_reticule(self, ctx, cx: int, cy: int, color: tuple[int, int, int]) -> None:
        e = _ARC_RADIUS + 5
        a = 6
        for sx in (-1, 1):
            for sy in (-1, 1):
                x = cx + sx * e
                y = cy + sy * e
                ctx.draw_line([(x, y), (x - sx * a, y)], fill=color, width=1)
                ctx.draw_line([(x, y), (x, y - sy * a)], fill=color, width=1)
