"""Shared Back / Bypass / Reset bottom row for ``PluginPanel`` children.

``FullscreenPluginPanel`` and ``PluginWindow`` render an identical three-button
row, just at different widths and font sizes. Kept as a free function rather
than a ``PluginPanel`` method — ``plugins.base.PluginPanel`` intentionally owns
no geometry, and this is pure layout, not shared state.
"""

from __future__ import annotations

from collections.abc import Callable

from uilib.box import Box
from uilib.text import Button
from uilib.widget import Widget

BTN_GAP = 2
BTN_H = 28

# Below this, three button labels start clipping/overlapping.
MIN_CHROME_WIDTH = 210


def build_bottom_row(
    *,
    parent: Widget,
    width: int,
    bottom_y: int,
    font,
    v_margin: int,
    on_back: Callable[..., None],
    on_bypass: Callable[..., None],
    on_reset: Callable[..., None],
) -> tuple[Button, Button, Button]:
    """Create a Back / Bypass / Reset row spanning *width*, parented to *parent*.

    *parent* is a panel when the row is fixed chrome, or a scrolling
    ``ContainerWidget`` when the row is the last thing in a scrolling body —
    it must be the real parent at construction, since ``Widget.attach`` is what
    puts a widget in a container's child list.

    Returns the three buttons in Nav order. Callers are responsible for
    ``add_sel_widget``.
    """
    btn_w = (width - 4 * BTN_GAP) // 3

    def _btn(text: str, x: int, action: Callable[..., None]) -> Button:
        return Button(
            box=Box.xywh(x, bottom_y, btn_w, BTN_H),
            text=text,
            font=font,
            v_margin=v_margin,
            outline_radius=4,
            parent=parent,
            action=action,
        )

    return (
        _btn("Back", BTN_GAP, on_back),
        _btn("Bypass", BTN_GAP * 2 + btn_w, on_bypass),
        _btn("Reset", BTN_GAP * 3 + btn_w * 2, on_reset),
    )
