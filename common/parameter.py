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

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import NewType, NotRequired, TypedDict
import json
import common.util as util

# strings as they appear in TTL files
TTL_ENUMERATION = "enumeration"
TTL_INTEGER = "integer"
TTL_LOGARITHMIC = "logarithmic"
TTL_PROPERTIES = "properties"
TTL_SCALEPOINTS = "scalePoints"
TTL_TAPTEMPO = "tapTempo"
TTL_TOGGLED = "toggled"

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


class MidiCC(TypedDict):
    """A port's MIDI-CC addressing, as mod-ui's pedalboard JSON and the
    midi_map WS message report it. channel -1 is the "unmapped" sentinel;
    hasRanges guards minimum/maximum for old bundles that predate the range
    fields (utils.py PedalboardMidiControl)."""

    channel: int
    control: int
    hasRanges: NotRequired[bool]
    minimum: NotRequired[float]
    maximum: NotRequired[float]


class PortInfo(TypedDict):
    """One row of an LV2 plugin's control-input ports, as mod-ui reports it."""

    symbol: str
    name: NotRequired[str]
    shortName: NotRequired[str]
    designation: NotRequired[str]
    ranges: NotRequired[Ranges]
    units: NotRequired[Units]
    properties: NotRequired[list[str]]
    scalePoints: NotRequired[list[ScalePoint]]


# mod-ui calls these "badports" and excludes them from its own GUI (mod/host.py),
# keeping their values in `valports`. We hide them the same way, for the same reason.
# The `enabled` port especially: mod-host writes the *inverse* of the bypass value
# into it (effects.c), so it isn't merely redundant with :bypass — it IS :bypass, and
# exposing it hands the user a knob that silently desyncs bypass.
HIDDEN_DESIGNATIONS = frozenset(
    {
        "http://lv2plug.in/ns/lv2core#enabled",
        "http://lv2plug.in/ns/lv2core#freeWheeling",
        "http://ardour.org/lv2/processing#enable",
        "http://lv2plug.in/ns/ext/time#beatsPerBar",
        "http://lv2plug.in/ns/ext/time#beatsPerMinute",
        "http://lv2plug.in/ns/ext/time#speed",
    }
)


def is_hidden_port(plugin_info: PortInfo) -> bool:
    """A port the plugin exposes but no UI should paint."""
    if "notOnGUI" in (plugin_info.get("properties") or []):
        return True
    return plugin_info.get("designation", "") in HIDDEN_DESIGNATIONS


class Type(Enum):
    DEFAULT = 0  # No explicitly defined type (eg. linear float)
    ENUMERATION = 1
    INTEGER = 2
    LOGARITHMIC = 3
    TAPTEMPO = 4
    TOGGLED = 5


class Parameter:
    def __init__(
        self,
        plugin_info: PortInfo,
        value: float,
        binding: str | None,
        instance_id: str | None = None,
        binding_range: tuple[float, float] | None = None,
    ):
        symbol = plugin_info.get("symbol")
        if not symbol:
            raise ValueError(f"LV2 port has no symbol: {plugin_info!r}")
        self.symbol: Symbol = Symbol(symbol)
        self.name: str = plugin_info.get("shortName") or plugin_info.get("name") or symbol
        self.hidden: bool = is_hidden_port(plugin_info)

        ranges = plugin_info.get("ranges") or Ranges()
        declared_minimum = float(ranges.get("minimum", 0.0))
        declared_maximum = float(ranges.get("maximum", 1.0))
        # minimum/maximum are the *effective* extents: the plugin's declared LV2
        # range, unless a MIDI-CC binding carries a custom sub-range
        self.minimum: float
        self.maximum: float
        self.minimum, self.maximum = binding_range or (declared_minimum, declared_maximum)
        # mod-ui normalises the TTL and always emits all three ranges; the
        # fallbacks only serve the params we synthesise (bypass, volume, VU).
        self.default: float = float(ranges.get("default", declared_minimum))

        # Reactive value: a property setter that notifies observers. _observers
        # must exist before the first assignment below, or the write fires into
        # a missing list.
        self._observers: list[Callable[[Parameter], None]] = []
        self._value: float = 0.0
        self.value = float(value)
        self.binding: str | None = binding
        self.instance_id: str | None = instance_id.lstrip("/") if instance_id else instance_id
        self.type = Type.DEFAULT
        self.enum_values: list[ScalePoint] = []
        # Logarithmic taper is independent of the discrete type: an integer
        # port can also be logarithmic (Degrade's Rate, Post Filter). The type
        # still drives step resolution (one notch per integer), but the graph
        # curve and the step taper follow the log flag.
        self.is_logarithmic: bool = False

        units_info = plugin_info.get("units") or Units()
        self.unit_symbol: str | None = units_info.get("symbol")
        self.unit_label: str | None = units_info.get("label")

        properties = plugin_info.get("properties") or []
        if len(properties) > 0:
            if TTL_LOGARITHMIC in properties:
                self.is_logarithmic = True
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

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, v: float) -> None:
        if v == self._value:
            return
        self._value = v
        for observe in self._observers:
            observe(self)

    def set_binding_range(self, binding_range: tuple[float, float]) -> None:
        """Set the effective extents from a MIDI-CC (sub-)range."""
        self.minimum, self.maximum = binding_range

    def subscribe(self, cb: Callable[[Parameter], None]) -> Callable[[], None]:
        """Register *cb* to fire on every changed-value write. Returns its own
        unsubscriber. An unchanged write (v == current) does not notify."""
        self._observers.append(cb)

        def _unsub() -> None:
            try:
                self._observers.remove(cb)
            except ValueError:
                pass

        return _unsub

    def get_enum_value_list(self) -> list[tuple[str, float]]:
        return [(v["label"], v["value"]) for v in self.enum_values]

    def is_ordered_enum(self) -> bool:
        """An enumeration that reads as a magnitude rather than a categorical
        pick: its scale points are a contiguous ascending integer ramp (Filter
        Order 1/2/3, Compressor Mode Light/Mild/Heavy). Only these map cleanly
        onto an arc ring — and ParameterSteps' even spacing across [min,max]
        assumes exactly this shape."""
        if self.type != Type.ENUMERATION or len(self.enum_values) < 2:
            return False
        return all(v["value"] == self.minimum + i for i, v in enumerate(self.enum_values))

    def format_value(self, value) -> str:
        """The numeric text alone. Callers that lay value and unit out
        separately (arc dials) need them unglued."""
        if self.type == Type.INTEGER or self.type == Type.TOGGLED or self.type == Type.ENUMERATION:
            return "%d" % round(float(value))
        return util.format_float(value)

    def format(self, value):
        text = self.format_value(value)
        if self.unit_symbol:
            text = f"{text} {self.unit_symbol}"
        return text

    def to_json(self):
        return json.dumps(self, default=json_default, sort_keys=True, indent=4)


def json_default(o):
    """``json.dumps`` default that strips reactive bookkeeping (_observers,
    _value) from Parameter and re-injects the public ``value``. Other objects
    serialize via __dict__ when available; types without it fall back to repr."""
    if isinstance(o, Parameter):
        d = {k: v for k, v in o.__dict__.items() if not k.startswith("_")}
        d["value"] = o._value
        return d
    if isinstance(o, frozenset):
        return list(o)
    if isinstance(o, Enum):
        return o.name
    try:
        return o.__dict__
    except AttributeError:
        return repr(o)
