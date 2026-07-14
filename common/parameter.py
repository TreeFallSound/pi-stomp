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

from enum import Enum
from typing import NewType, NotRequired, TypedDict
import json
import common.util as util

# strings as they appear in TTL files
TTL_ENUMERATION = 'enumeration'
TTL_INTEGER     = 'integer'
TTL_LOGARITHMIC = 'logarithmic'
TTL_PROPERTIES  = 'properties'
TTL_SCALEPOINTS = 'scalePoints'
TTL_TAPTEMPO    = 'tapTempo'
TTL_TOGGLED     = 'toggled'

# Identifies a Parameter: the key of plugin.parameters, ParamEffect.symbol,
# edit_symbol(). Usually an LV2 port symbol (":bypass", "gain"); also an ALSA
# mixer control ("MASTER") or a synthesized id ("external_1_7"). Never a
# shortName — that's free text, and the two coincide often enough to hide it.
Symbol = NewType("Symbol", str)

BYPASS_SYMBOL = Symbol(":bypass")


class Ranges(TypedDict):
    minimum: NotRequired[float]
    maximum: NotRequired[float]
    default: NotRequired[float]


class Units(TypedDict):
    symbol: NotRequired[str]
    label: NotRequired[str]


class ScalePoint(TypedDict):
    label: str
    value: float


class PortInfo(TypedDict):
    """One row of an LV2 plugin's control-input ports, as mod-ui reports it."""
    symbol: str
    name: NotRequired[str]
    shortName: NotRequired[str]
    ranges: NotRequired[Ranges]
    units: NotRequired[Units]
    properties: NotRequired[list[str]]
    scalePoints: NotRequired[list[ScalePoint]]


class Type(Enum):
    DEFAULT = 0      # No explicitly defined type (eg. linear float)
    ENUMERATION = 1
    INTEGER = 2
    LOGARITHMIC = 3
    TAPTEMPO = 4
    TOGGLED = 5

class Parameter:

    def __init__(self, plugin_info: PortInfo, value: float, binding: str | None, instance_id: str | None = None):
        symbol = plugin_info.get("symbol")
        if not symbol:
            raise ValueError(f"LV2 port has no symbol: {plugin_info!r}")
        self.symbol: Symbol = Symbol(symbol)
        self.name: str = plugin_info.get("shortName") or plugin_info.get("name") or symbol

        ranges = plugin_info.get("ranges") or Ranges()
        self.minimum: float = float(ranges.get("minimum", 0.0))
        self.maximum: float = float(ranges.get("maximum", 1.0))
        # mod-ui normalises the TTL and always emits all three ranges; the
        # fallbacks only serve the params we synthesise (bypass, volume, VU).
        self.default: float = float(ranges.get("default", self.minimum))

        self.value: float = float(value)
        self.binding: str | None = binding
        self.instance_id: str | None = instance_id.lstrip("/") if instance_id else instance_id
        self.type = Type.DEFAULT
        self.enum_values: list[ScalePoint] = []

        units_info = plugin_info.get("units") or Units()
        self.unit_symbol: str | None = units_info.get("symbol")
        self.unit_label: str | None = units_info.get("label")

        properties = plugin_info.get("properties") or []
        if len(properties) > 0:
            if TTL_ENUMERATION in properties:
                self.enum_values = plugin_info.get("scalePoints") or []
                self.type = Type.ENUMERATION
            elif TTL_INTEGER in properties:
                self.type = Type.INTEGER
            elif TTL_LOGARITHMIC in properties:
                self.type = Type.LOGARITHMIC
            elif TTL_TAPTEMPO in properties:
                self.type = Type.TAPTEMPO
            elif TTL_TOGGLED in properties:
                self.type = Type.TOGGLED

    def get_enum_value_list(self) -> list[tuple[str, float]]:
        return [(v["label"], v["value"]) for v in self.enum_values]

    def get_taper(self):
        return 2 if self.type == Type.LOGARITHMIC else 1

    def format(self, value):
        if self.type == Type.INTEGER or self.type == Type.TOGGLED or self.type == Type.ENUMERATION:
             text = "%d" % round(float(value))
        else:
             text = util.format_float(value)

        if self.unit_symbol:
            text = f"{text} {self.unit_symbol}"
        return text

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)
