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

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import ImageColor

from uilib import TextHAlign

import pistomp.config_overrides as overrides

_COLOR_BRIGHT: tuple = (255, 255, 255)
_COLOR_DIM: tuple = (160, 160, 160)

LongpressAction = Literal[
    "next_snapshot",
    "previous_snapshot",
    "toggle_bypass",
    "set_mod_tap_tempo",
    "toggle_tap_tempo_enable",
]
LONGPRESS_ACTIONS: list[LongpressAction] = [
    "next_snapshot",
    "previous_snapshot",
    "toggle_bypass",
    "set_mod_tap_tempo",
    "toggle_tap_tempo_enable",
]

# 12 colors chosen from CSS named colors; all accepted by PIL ImageColor.getrgb().
COLOR_PALETTE: list[str] = [
    "Red",
    "Orange",
    "Yellow",
    "YellowGreen",
    "Green",
    "Cyan",
    "SteelBlue",
    "Blue",
    "MediumVioletRed",
    "Violet",
    "White",
    "Silver",
]

TargetType = Literal["footswitch", "encoder"]
FieldName = Literal["longpress", "color", "disable"]


@dataclass
class EditorRow:
    target: TargetType
    index: int
    field: FieldName
    current_value: Any
    default_value: Any
    choices: list[str]

    @property
    def label(self) -> str:
        prefix = f"FS{self.index}" if self.target == "footswitch" else f"Enc{self.index}"
        if self.current_value is None:
            dv = str(self.default_value) if self.default_value is not None else "none"
            val_str = f"({dv})"
        else:
            val_str = str(self.current_value)
        return f"{prefix} {self.field}: {val_str}"


class PedalboardConfigEditor:

    def __init__(self, modhandler: Any, hardware: Any, lcd: Any) -> None:
        self.handler = modhandler
        self.hardware = hardware
        self.lcd = lcd
        self._menu = None

    def open(self) -> None:
        rows = self._build_menu_model()
        items = [
            (row.label, self._on_row_select, row, False,
             _COLOR_DIM if row.current_value is None else _COLOR_BRIGHT)
            for row in rows
        ]
        self._menu = self.lcd.draw_selection_menu(items, "Pedalboard Config",
                                                  dismiss_option=True,
                                                  text_halign=TextHAlign.LEFT)

    def _build_menu_model(self) -> list[EditorRow]:
        bundle = Path(self.handler.current.pedalboard.bundle)
        override_doc = overrides.load_override(bundle)
        default_cfg = self.hardware.default_cfg
        rows: list[EditorRow] = []

        for fs in self.hardware.footswitches:
            idx: int = fs.id
            for field_name in ("longpress", "color", "disable"):
                field: FieldName = field_name  # type: ignore[assignment]
                current = overrides.get_effective(default_cfg, override_doc, "footswitch", idx, field_name)
                default = _default_value(default_cfg, "footswitch", idx, field_name)
                match field_name:
                    case "longpress":
                        choices: list[str] = list(LONGPRESS_ACTIONS)
                    case "color":
                        choices = list(COLOR_PALETTE)
                    case "disable":
                        choices = ["true", "false"]
                rows.append(EditorRow("footswitch", idx, field, current, default, choices))

        for enc in self.hardware.encoders:
            if enc is None or getattr(enc, "id", None) is None:
                continue
            idx = enc.id
            current = overrides.get_effective(default_cfg, override_doc, "encoder", idx, "longpress")
            default = _default_value(default_cfg, "encoder", idx, "longpress")
            rows.append(EditorRow("encoder", idx, "longpress", current, default, list(LONGPRESS_ACTIONS)))

        return rows

    def _on_row_select(self, row: EditorRow) -> None:
        dv = str(row.default_value) if row.default_value is not None else "none"
        use_default_label = f"(use default: {dv})"
        items: list[tuple] = [
            (use_default_label, self._on_value_chosen, (row, overrides.UNSET),
             row.current_value is None, _COLOR_DIM),
        ]
        for choice in row.choices:
            checked = row.current_value is not None and choice == str(row.current_value)
            color = _choice_color(row.field, choice)
            items.append((choice, self._on_value_chosen, (row, choice), checked, color))
        self.lcd.draw_selection_menu(items, row.label, auto_dismiss=True,
                                     text_halign=TextHAlign.LEFT)

    def _on_value_chosen(self, arg: tuple) -> None:
        row, new_value = arg
        bundle = Path(self.handler.current.pedalboard.bundle)
        doc = overrides.load_override(bundle) or {}
        if new_value is overrides.UNSET:
            overrides.set_field(doc, row.target, row.index, row.field, overrides.UNSET)
        else:
            overrides.set_field(doc, row.target, row.index, row.field, _coerce(row.field, new_value))
        overrides.write_override(bundle, doc)
        if self._menu is not None:
            self._menu._dismiss()
        self.handler.set_current_pedalboard(self.handler.current.pedalboard)


def _default_value(cfg: dict, target: str, index: int, field: str) -> Any:
    list_key = "footswitches" if target == "footswitch" else "encoders"
    for entry in cfg.get("hardware", {}).get(list_key, []):
        if entry.get("id") == index:
            return entry.get(field)
    return None


def _coerce(field: FieldName, value: str) -> Any:
    match field:
        case "disable":
            return value.lower() == "true"
        case _:
            return value


def _choice_color(field: FieldName, choice: str) -> tuple | None:
    if field == "color":
        try:
            return ImageColor.getrgb(choice)
        except ValueError:
            pass
    return None
