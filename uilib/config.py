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

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from uilib.pygame_init import font as _make_font

if TYPE_CHECKING:
    import pygame._freetype

_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"

Color = tuple[int, int, int]


class Config:
    _instance: "Config | None" = None

    fonts: dict[str, "pygame._freetype.Font"]
    colors: dict[str, Color]

    def __new__(cls, _config_json: str | None = None) -> "Config":
        if Config._instance is None:
            Config._instance = super().__new__(cls)
        return Config._instance

    def __init__(self, config_json: str | None = None) -> None:
        if not hasattr(self, "fonts"):
            print("Adding empty fonts...")
            self.fonts = {}
        if not hasattr(self, "colors"):
            print("Adding empty colors...")
            self.colors = {}
        if config_json is not None:
            self.load_config(config_json)
        self._set_defaults()

    def _set_defaults(self) -> None:
        if "default" not in self.fonts:
            self.add_font("default", "DejaVuSans.ttf", 16)
        if "default_title" not in self.fonts:
            self.add_font("default_title", "DejaVuSans-Bold.ttf", 16)
        if "footswitch" not in self.fonts:
            self.add_font("footswitch", "DejaVuSans.ttf", 18)
        if "default_fgnd" not in self.colors:
            self.add_color("default_fgnd", (255, 255, 255))
        if "default_bkgnd" not in self.colors:
            self.add_color("default_bkgnd", (0, 0, 0))
        if "default_title_fgnd" not in self.colors:
            self.add_color("default_title_fgnd", (255, 191, 63))
        if "default_title_bkgnd" not in self.colors:
            self.add_color("default_title_bkgnd", (63, 63, 63))

    def add_font(self, label: str, file_name: str, size: int) -> None:
        # Resolve bare filenames against the bundled fonts directory.
        path: str = file_name
        if not os.path.isabs(file_name) and not os.path.exists(file_name):
            candidate = _FONTS_DIR / file_name
            if candidate.exists():
                path = str(candidate)
        self.fonts[label] = _make_font(path, size)

    def get_font(self, label: str) -> "pygame._freetype.Font | None":
        return self.fonts.get(label)

    def has_font(self, label: str) -> bool:
        return label in self.fonts

    def add_color(self, label: str, rgb: Color) -> None:
        self.colors[label] = rgb

    def get_color(self, label: str) -> Color:
        return self.colors[label]

    def has_color(self, label: str) -> bool:
        return label in self.colors

    def load_config(self, json_file: str, reset_old: bool = True) -> None:
        if reset_old:
            self.fonts = {}
            self.colors = {}
        with open(json_file, "r") as f:
            data: dict = json.load(f)
        if "fonts" in data:
            for font_def in data["fonts"]:
                try:
                    label: str = font_def["label"]
                    name: str = font_def["name"]
                    size: int = font_def["size"]
                except KeyError as e:
                    print("Error loading font:", e)
                else:
                    self.add_font(label, name, size)
        if "colors" in data:
            for color_def in data["colors"]:
                try:
                    label = color_def["label"]
                    rgb: Color = tuple(color_def["rgb"])
                except KeyError as e:
                    print("Error loading color:", e, data["colors"])
                else:
                    self.add_color(label, rgb)
