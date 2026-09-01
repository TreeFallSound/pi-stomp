# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pistomp.controller import ControlType, Controller
from plugins.chrome import BTN_GAP, BTN_H
from uilib import Box, Config, Dialog, TextWidget, WidgetAlign, get_text_size
from uilib.misc import InputEvent
from uilib.pygame_init import font as _make_font
from uilib.text import Button

if TYPE_CHECKING:
    from pistomp.lcd320x240 import Lcd

_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"

WIDTH = 220
LINE_H = 18
ROW_PAD = 4


def control_name(control: Controller) -> str:
    """The short name of one input, by what it does and where it sits."""
    if control.type is ControlType.EXPRESSION:
        return "EXP"
    if control.type is ControlType.VOLUME:
        return "VOL"
    return f"K{control.id}"


def _detail(lcd: "Lcd", control: Controller) -> str:
    if control.type is ControlType.VOLUME:
        return "output volume"
    if control.midi_CC is None:
        return "unassigned"
    port_name = lcd.handler.hardware.external_port_name(control)
    if port_name is not None:
        return f"{port_name}:{control.midi_CC}"
    return f"CC {control.midi_CC}"


def _row_text(lcd: "Lcd", control: Controller) -> str:
    state = "off" if control.disabled else "on"
    return f"{control_name(control)}  {_detail(lcd, control)}{TextWidget.SPLIT_SEP}{state}"


class AnalogMenu:
    """Shows every analog input and encoder with its resolved binding, and
    turns one on or off."""

    def __init__(self, lcd: "Lcd") -> None:
        self.lcd = lcd
        self._panel: Dialog | None = None

    def controls(self) -> list[Controller]:
        hardware = self.lcd.handler.hardware
        rows = [c for c in hardware.analog_controls + hardware.encoders if c.type is not ControlType.NAV]
        return sorted(rows, key=lambda c: c.id if c.id is not None else 0)

    def open(self) -> None:
        controls = self.controls()
        height = min(220, 2 * ROW_PAD + LINE_H * len(controls) + BTN_H + 12)

        d = Dialog(width=WIDTH, height=height, title="Analog Inputs", auto_destroy=True)
        font = _make_font(_FONTS_DIR / "DejaVuSans.ttf", 14)

        y = ROW_PAD
        for control in controls:
            TextWidget(
                box=Box.xywh(8, y, WIDTH - 16, LINE_H),
                text=_row_text(self.lcd, control),
                font=font,
                parent=d,
                outline=0,
                sel_width=1,
                align=WidgetAlign.NONE,
                object=control,
                action=self._toggle,
            )
            y += LINE_H
        for row in d.children:
            if isinstance(row, TextWidget) and row.object is not None:
                d.add_sel_widget(row)

        btn_font = Config().get_font("small")
        _, btn_text_h = get_text_size("Back", btn_font)
        btn_w = (WIDTH - 4 * BTN_GAP) // 3
        back_btn = Button(
            box=Box.xywh((WIDTH - btn_w) // 2, height - BTN_H - 6, btn_w, BTN_H),
            text="Back",
            font=btn_font,
            v_margin=max(0, (BTN_H - btn_text_h) // 2),
            outline_radius=4,
            parent=d,
            action=self._on_back,
            name="analog_menu_back_btn",
        )
        d.add_sel_widget(back_btn)

        self._panel = d
        self.lcd.pstack.push_panel(d)
        d.refresh()

    def _toggle(self, _event: InputEvent, widget: TextWidget, control: Controller) -> None:
        self.lcd.handler.hardware.set_input_enabled(control, control.disabled)
        widget.set_text(_row_text(self.lcd, control))
        if self._panel is not None:
            self._panel.refresh()
        self.lcd.refresh_analog_row()

    def _on_back(self, _event: object = None, _widget: object = None) -> None:
        if self._panel is not None:
            old = self._panel
            self._panel = None
            self.lcd.pstack.pop_panel(old)
