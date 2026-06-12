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

"""Type definitions for blend mode."""

from dataclasses import dataclass
from typing import Any, Callable, NamedTuple, NotRequired, Protocol, TypeAlias, TypedDict

from modalapi.parameter import Type as ParameterType


# Domain identifiers. These are all `str` at runtime; the aliases exist so that
# `dict[InstanceId, dict[Symbol, ParamData]]` reads as documentation.
InstanceId: TypeAlias = str  # e.g. "BigMuffPi" (canonical, no leading slash)
Symbol: TypeAlias = str  # e.g. "Tone", ":bypass"
PositionKey: TypeAlias = str  # stringified float, e.g. "0.0", "0.5"
SnapshotRef: TypeAlias = int | str  # snapshot index or name


class BlendSnapshotConfig(TypedDict):
    """Single blend snapshot configuration from YAML."""

    name: str
    input_id: int
    interpolation: NotRequired[str]
    stops: dict[PositionKey, SnapshotRef] | list[SnapshotRef]


NormalizedStops: TypeAlias = dict[PositionKey, SnapshotRef]
MidiBoundParams: TypeAlias = set[tuple[InstanceId, Symbol]]


class PluginData(TypedDict):
    bypassed: bool
    parameters: dict[str, Any]
    ports: dict[Symbol, float]
    preset: str
    bpm: NotRequired[float]
    bpb: NotRequired[float]


class SnapshotData(TypedDict):
    name: str
    data: dict[InstanceId, PluginData]


class SnapshotsJson(TypedDict):
    current: int
    snapshots: list[SnapshotData]


class ParameterKey(NamedTuple):
    instance_id: InstanceId
    symbol: Symbol


class BlendInputProtocol(Protocol):
    """Protocol for blend mode input sources (expression pedal or encoder)."""

    id: int

    def get_normalized_value(self) -> float: ...


class WebSocketBridgeProtocol(Protocol):
    def send_parameter(self, instance_id: InstanceId, symbol: Symbol, value: float) -> bool: ...
    def clear_queue(self) -> int: ...


SnapshotStateDict: TypeAlias = dict[InstanceId, dict[Symbol, float]]
ParameterTypeGetter: TypeAlias = Callable[[InstanceId, Symbol], ParameterType]


@dataclass
class ParamData:
    """Pre-computed parameter data for a differing parameter between two stops."""

    val_a: float
    val_b: float
    param_type: ParameterType


EnrichedDiffMap: TypeAlias = dict[InstanceId, dict[Symbol, ParamData]]
