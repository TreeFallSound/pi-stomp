# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Footswitch long-press bindings menu.

A read-only list, opened by long-pressing the footswitch bar: single-switch
longpress actions, a divider, then the chords. The pedalboard's own config.yml
shadows default_config.yml per footswitch id, as Hardware.__init_footswitches
does. Built directly on Dialog (like EthernetMenu/WifiMenu) rather than
ModalDialog/PluginPanel — there's no Plugin or reactive parameter state behind
a static config listing.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

import common.token as Token
from uilib import Box, Dialog, TextWidget, WidgetAlign
from uilib.paint import PaintContext
from uilib.pygame_init import font as _make_font

if TYPE_CHECKING:
    from pistomp.lcd320x240 import Lcd

_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"

WIDTH = 220
LINE_H = 18
ROW_PAD = 4
DIVIDER_H = 8
BTN_H = 24

# Only the string/list longpress enum (pistomp/config.py schema); the mapping
# form (midi_CC/preset/pedalboard) is handled separately by _label_for_mapping.
_ACTION_LABELS = {
    "next_snapshot": "Snapshot +",
    "previous_snapshot": "Snapshot -",
    "toggle_bypass": "Toggle Bypass",
    "set_mod_tap_tempo": "Tap Tempo",
    "toggle_tap_tempo_enable": "Tap Tempo On/Off",
    "toggle_tuner_enable": "Tuner",
}


def _label_for_action(name: str) -> str:
    return _ACTION_LABELS.get(name, name)


def _label_for_mapping(action: dict[str, Any]) -> str:
    if Token.MIDI_CC in action:
        return f"MIDI CC {action[Token.MIDI_CC]}"
    if Token.PRESET in action:
        value = action[Token.PRESET]
        if value == Token.UP:
            return "Preset +"
        if value == Token.DOWN:
            return "Preset -"
        return f"Preset {value}"
    value = action["pedalboard"]
    return "Pedalboard +" if value == Token.UP else "Pedalboard -"


def _rows_from_entries(entries: list[dict[str, Any]], id_to_letter: dict[int, str]) -> list[tuple[str, str]]:
    """(letters, label) rows: footswitches sharing a string/list longpress
    name chord together (FootswitchChords groups by name); a mapping-form
    longpress is always its own row — it never joins a named group (see
    Footswitch.set_longpress_groups)."""
    groups: dict[object, list[int]] = {}
    labels: dict[object, str] = {}
    for entry in entries:
        longpress = entry.get(Token.LONGPRESS)
        if longpress is None:
            continue
        fs_id = entry[Token.ID]
        if isinstance(longpress, dict):
            groups.setdefault(fs_id, []).append(fs_id)
            labels[fs_id] = _label_for_mapping(longpress)
        else:
            names = longpress.split() if isinstance(longpress, str) else longpress
            for name in names:
                groups.setdefault(name, []).append(fs_id)
                labels[name] = _label_for_action(name)

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


def _pedalboard_footswitch_entries(bundle: str) -> tuple[list[dict[str, Any]], set[int]]:
    """Raw footswitch entries from this pedalboard's own config.yml, and the
    full set of ids it touches — including entries with no longpress: of
    their own, since Hardware.__init_footswitches's clear_pedalboard_info()
    wipes any *default* longpress for those ids too."""
    config_file = Path(bundle) / "config.yml"
    if not config_file.exists():
        return [], set()
    with open(config_file, "r") as f:
        cfg = yaml.load(f, Loader=yaml.SafeLoader)
    entries = ((cfg or {}).get(Token.HARDWARE) or {}).get(Token.FOOTSWITCHES) or []
    return entries, {e[Token.ID] for e in entries}


class _BindingsDialog(Dialog):
    divider_y: int | None = None
    divider_color = (70, 70, 70)

    def _draw(self, ctx: PaintContext) -> None:
        super()._draw(ctx)
        if self.divider_y is not None:
            ctx.draw_rectangle(Box.xywh(8, self.divider_y, ctx.width - 16, 1), fill=self.divider_color)


class FootswitchMenu:
    """Opened by long-pressing the footswitch bar. Mirrors EthernetMenu: a
    single Dialog pushed onto the panel stack, dismissed by its own Back
    button — content is rebuilt fresh on every open() rather than tracked
    live, since it only depends on the pedalboard that's already current."""

    def __init__(self, lcd: "Lcd") -> None:
        self.lcd = lcd
        self._panel: Dialog | None = None

    def open(self) -> None:
        hardware = self.lcd.handler.hardware
        default_entries = hardware.default_cfg[Token.HARDWARE][Token.FOOTSWITCHES]
        id_to_letter = {e[Token.ID]: chr(ord("A") + e[Token.ID]) for e in default_entries}

        bundle = self.lcd.handler.current.pedalboard.bundle
        pb_entries, pb_ids = _pedalboard_footswitch_entries(bundle)
        merged = [e for e in default_entries if e[Token.ID] not in pb_ids] + pb_entries
        single_rows, chord_rows = _partition_rows(_rows_from_entries(merged, id_to_letter))

        show_divider = bool(single_rows) and bool(chord_rows)
        num_rows = len(single_rows) + len(chord_rows)
        height = min(220, 2 * ROW_PAD + LINE_H * num_rows + (DIVIDER_H if show_divider else 0) + BTN_H + 12)

        d = _BindingsDialog(width=WIDTH, height=height, title="Footswitch Bindings", auto_destroy=True)
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

        back_btn = TextWidget(
            box=Box.xywh(8, height - BTN_H - 6, 0, 0),
            text="Back",
            parent=d,
            outline=1,
            sel_width=3,
            outline_radius=5,
            action=self._on_back,
            align=WidgetAlign.NONE,
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
