from __future__ import annotations

from collections.abc import Callable

from common.parameter import Parameter
from uilib.box import Box
from uilib.config import Config
from uilib.misc import InputEvent, get_text_size
from uilib.widget import Widget

_BAR_H = 3
_BAR_Y_OFFSET = 6
_TOP_PADDING = 4

_BG = (0, 0, 0)
_LABEL_FG = (255, 255, 255)
_BAR_EMPTY = (45, 45, 45)
_BAR_FILL = (255, 230, 80)


class ModeSelectorWidget(Widget):
    symbol: str = "mode"

    def __init__(
        self,
        box: Box,
        param: Parameter,
        handler,
        set_param: Callable[[str, float], None],
        on_change: Callable[[int], None] | None = None,
        **kwargs,
    ) -> None:
        kwargs.setdefault("bkgnd_color", _BG)
        super().__init__(box=box, **kwargs)
        self._param = param
        self._handler = handler
        self._set_param = set_param
        self._on_change = on_change
        cfg = Config()
        self._font = cfg.get_font("footswitch")
        self._value: int = 0
        self._labels: list[str] = []
        self._max: int = 42

        if param.enum_values:
            labels = [item[0] for item in param.get_enum_value_list()]
        else:
            labels = [str(i) for i in range(int(param.maximum) - int(param.minimum) + 1)]
        self.set_labels(labels)

    @property
    def value(self) -> int:
        return self._value

    @property
    def max_index(self) -> int:
        return self._max

    def set_value(self, value: int) -> None:
        value = max(0, min(self._max, int(value)))
        if value == self._value and self._labels:
            return
        self._value = value
        self.refresh()

    def set_labels(self, labels: list[str]) -> None:
        self._labels = labels
        self._max = max(len(labels) - 1, 1)
        self.refresh()

    def input_event(self, event) -> bool:
        if event == InputEvent.CLICK:
            self._open_dialog()
            return True
        return False

    def _open_dialog(self) -> None:
        lcd = self._handler.lcd
        if lcd is None:
            return
        current_value = self._param.value
        default_item: str | None = None
        items = []
        for label, value in self._param.get_enum_value_list():
            selected = value == current_value
            if selected:
                default_item = f"\u2714 {label}"
            items.append((label, self._commit_value, value, selected))
        title = f"{self._param.instance_id}:{self._param.name}"
        lcd.draw_selection_menu(items, title, auto_dismiss=True, default_item=default_item)

    def _commit_value(self, value: float) -> None:
        new_mode = int(value)
        self._set_param(self.symbol, float(new_mode))
        self.set_value(new_mode)
        if self._on_change is not None:
            self._on_change(new_mode)

    def _draw_erase(self, ctx) -> None:
        ctx.draw_rectangle(ctx.dirty_bounds, fill=_BG)

    def _draw(self, ctx) -> None:
        if not self._labels:
            return
        label = self._labels[self._value] if self._value < len(self._labels) else "?"
        text = f"\u2039  {label}  \u203a"

        tw, th = get_text_size(text, self._font)
        cx = ctx.width // 2
        ty = _TOP_PADDING

        ctx.draw_text((cx - tw // 2, ty), text, fill=_LABEL_FG, font=self._font)

        bar_y = ty + th + _BAR_Y_OFFSET
        bar_x0 = 4
        bar_x1 = ctx.width - 4
        bar_w = bar_x1 - bar_x0

        ctx.draw_rectangle(Box(bar_x0, bar_y, bar_x1, bar_y + _BAR_H), fill=_BAR_EMPTY)

        if self._max > 0:
            fill_w = int(bar_w * (self._value / self._max))
            if fill_w > 0:
                ctx.draw_rectangle(Box(bar_x0, bar_y, bar_x0 + fill_w, bar_y + _BAR_H), fill=_BAR_FILL)
