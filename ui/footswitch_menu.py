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
from typing import TYPE_CHECKING, Sequence

from pistomp.config.model import (
    FootswitchBinding,
    MINUS,
)
from plugins.chrome import BTN_GAP, BTN_H
from uilib import Box, Config, Dialog, TextWidget, WidgetAlign, get_text_size
from uilib.paint import PaintContext
from uilib.pygame_init import font as _make_font
from uilib.text import Button

if TYPE_CHECKING:
    from pistomp.lcd320x240 import Lcd

_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"

WIDTH = 220
LINE_H = 18
ROW_PAD = 4
DIVIDER_H = 8

# Chord-form action names. The mapping form makes its own label.
_ACTION_LABELS = {
    "next_snapshot": "Snapshot +",
    "previous_snapshot": f"Snapshot {MINUS}",
    "next_pedalboard": "Pedalboard +",
    "previous_pedalboard": f"Pedalboard {MINUS}",
    "toggle_bypass": "Toggle Bypass",
    "toggle_tap_tempo_enable": "Tap Tempo",
    "toggle_tuner_enable": "Tuner",
}


def _label_for_action(name: str) -> str:
    return _ACTION_LABELS.get(name, name)

def _rows_from_bindings(bindings: Sequence[FootswitchBinding], id_to_letter: dict[int, str]) -> list[tuple[str, str]]:
    """(letters, label) rows: footswitches that share a longpress name chord
    together. A mapping-form longpress is always its own row."""
    groups: dict[object, list[int]] = {}
    labels: dict[object, str] = {}
    for binding in bindings:
        longpress = binding.longpress
        if longpress is None:
            continue
        if isinstance(longpress, tuple):
            for name in longpress:
                groups.setdefault(name, []).append(binding.id)
                labels[name] = _label_for_action(name)
        else:
            groups.setdefault(binding.id, []).append(binding.id)
            labels[binding.id] = longpress.label()

    rows = []
    for key, ids in groups.items():
        ids.sort()
        letters = "+".join(id_to_letter[i] for i in ids)
        rows.append((tuple(ids), letters, labels[key]))
    rows.sort(key=lambda r: r[0])
    return [(letters, label) for _, letters, label in rows]


def _partition_rows(rows: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    singles = [r for r in rows if "+" not in r[0]]
    chords = [r for r in rows if "+" in r[0]]
    return singles, chords


class _BindingsDialog(Dialog):
    divider_y: int | None = None
    divider_color = (70, 70, 70)

    def _draw(self, ctx: PaintContext) -> None:
        super()._draw(ctx)
        if self.divider_y is not None:
            ctx.draw_rectangle(Box.xywh(8, self.divider_y, ctx.width - 16, 1), fill=self.divider_color)


class FootswitchMenu:
    """Shows the long-press bindings for all footswitches, grouped by name."""

    def __init__(self, lcd: "Lcd") -> None:
        self.lcd = lcd
        self._panel: Dialog | None = None

    def open(self) -> None:
        bindings = self.lcd.handler.hardware.config.footswitches
        id_to_letter = {b.id: chr(ord("A") + b.id) for b in bindings}
        single_rows, chord_rows = _partition_rows(_rows_from_bindings(bindings, id_to_letter))

        show_divider = bool(single_rows) and bool(chord_rows)
        num_rows = len(single_rows) + len(chord_rows)
        height = min(220, 2 * ROW_PAD + LINE_H * num_rows + (DIVIDER_H if show_divider else 0) + BTN_H + 12)

        d = _BindingsDialog(width=WIDTH, height=height, title="Longpress Bindings", auto_destroy=True)
        font = _make_font(_FONTS_DIR / "DejaVuSans.ttf", 14)

        y = ROW_PAD
        for letters, label in single_rows:
            TextWidget(
                box=Box.xywh(8, y, WIDTH - 16, LINE_H),
                text=letters + TextWidget.SPLIT_SEP + label,
                font=font,
                parent=d,
                outline=0,
                sel_width=0,
                align=WidgetAlign.NONE,
            )
            y += LINE_H
        if show_divider:
            d.divider_y = y + DIVIDER_H // 2
            y += DIVIDER_H
        for letters, label in chord_rows:
            TextWidget(
                box=Box.xywh(8, y, WIDTH - 16, LINE_H),
                text=letters + TextWidget.SPLIT_SEP + label,
                font=font,
                parent=d,
                outline=0,
                sel_width=0,
                align=WidgetAlign.NONE,
            )
            y += LINE_H

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
            name="footswitch_menu_back_btn",
        )
        d.add_sel_widget(back_btn)

        self._panel = d
        self.lcd.pstack.push_panel(d)
        d.refresh()

    def _on_back(self, _event: object = None, _widget: object = None) -> None:
        if self._panel is not None:
            old = self._panel
            self._panel = None
            self.lcd.pstack.pop_panel(old)
