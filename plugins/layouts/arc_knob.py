from __future__ import annotations

from uilib.box import Box
from uilib.glyphs.arc_dial import ArcDialWidget, DialFormatter
from uilib.misc import InputEvent
from uilib.widget import Widget

_RING_RADIUS = 32
_LABEL_FG = (180, 180, 180)


class ArcKnobWidget(ArcDialWidget):
    """Single rotary knob for the fullscreen plugin panels. Click resets to
    the pedalboard default via the owning panel."""

    def __init__(
        self,
        *,
        box: Box,
        symbol: str,
        label: str,
        color: tuple[int, int, int],
        minimum: float,
        maximum: float,
        formatter: DialFormatter,
        panel,
        parent: Widget | None = None,
        **kwargs,
    ) -> None:
        super().__init__(
            box=box,
            label=label,
            minimum=minimum,
            maximum=maximum,
            color=color,
            formatter=formatter,
            parent=parent if parent is not None else panel,
            radius=_RING_RADIUS,
            label_fg=_LABEL_FG,
            **kwargs,
        )
        self.symbol = symbol
        self._panel = panel

    def input_event(self, event) -> bool:
        if event == InputEvent.CLICK:
            self._panel._reset_to_default(self.symbol)
            return True
        return False
