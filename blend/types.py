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
from typing import Any, Callable, NamedTuple, NotRequired, Protocol, TypedDict

from modalapi.parameter import Type as ParameterType


# Config TypedDicts
class BlendSnapshotConfig(TypedDict):
    """Single blend snapshot configuration from YAML."""

    name: str  # Required - snapshot name
    input_id: int  # Required - analog control or encoder ID
    interpolation: NotRequired[str]  # Optional - default: "linear"
    stops: dict[str, int | str] | list[str | int]  # Dict or list format


class PedalboardBlendConfig(TypedDict):
    """Pedalboard-level blend configuration containing multiple blend snapshots."""

    blend_snapshots: list[BlendSnapshotConfig]


# Type alias for normalized stops (always dict format after normalization)
NormalizedStops = dict[str, int | str]  # "position" -> snapshot (index or name)

# Type alias for MIDI-bound parameters (excluded from interpolation)
MidiBoundParams = set[tuple[str, str]]  # {(instance_id, symbol)}


# Snapshots.json TypedDicts
class PluginData(TypedDict):
    """Plugin data from snapshots.json."""

    bypassed: bool
    parameters: dict[str, Any]
    ports: dict[str, float]
    preset: str
    bpm: NotRequired[float]
    bpb: NotRequired[float]


class SnapshotData(TypedDict):
    """Single snapshot entry from snapshots.json."""

    name: str
    data: dict[str, PluginData]


class SnapshotsJson(TypedDict):
    """Complete snapshots.json file structure."""

    current: int
    snapshots: list[SnapshotData]


# State TypedDicts
class ParameterState(TypedDict):
    """Parameter values for a plugin: {symbol: value}"""

    pass  # Dict[str, float] - dynamic keys


class SnapshotState(TypedDict):
    """Complete snapshot state: {instance_id: {symbol: value}}"""

    pass  # Dict[str, Dict[str, float]] - dynamic keys


class DiffMapEntry(TypedDict):
    """Single parameter diff entry: (val_a, val_b, param_type)"""

    pass  # Tuple[float, float, ParameterType] - but TypedDict doesn't support tuples


# NamedTuple for intermediate data structures
class StopData(NamedTuple):
    """Intermediate representation of a stop during parsing."""

    position: float
    snapshot_index: int


class ParameterKey(NamedTuple):
    """Key for identifying a unique parameter in MIDI de-duplication tracking."""

    instance_id: str
    symbol: str


# Protocol types for external dependencies
class BlendInputProtocol(Protocol):
    """Protocol for blend mode input sources (expression pedal or encoder)."""

    id: int
    value_change_callback: Callable[[int, Any], None] | None

    def get_normalized_value(self) -> float:
        """Return current value normalized to [0.0, 1.0]."""
        ...


# Backwards compatibility alias
AnalogControlProtocol = BlendInputProtocol


class WebSocketBridgeProtocol(Protocol):
    """Protocol for WebSocket bridge interface."""

    def send_parameter(self, instance_id: str, symbol: str, value: float) -> bool: ...
    def clear_queue(self) -> int: ...


# Type aliases for complex nested structures
ParameterStateDict = dict[str, float]
SnapshotStateDict = dict[str, ParameterStateDict]
DiffMapDict = dict[str, dict[str, tuple[float, float, ParameterType]]]
ParameterTypeGetter = Callable[[str, str], ParameterType]


# Pre-computed parameter data
@dataclass
class ParamData:
    """Pre-computed parameter data for a differing parameter between two stops."""

    val_a: float       # Value at lower stop
    val_b: float       # Value at upper stop
    param_type: ParameterType


# Enriched diff map type
EnrichedDiffMap = dict[str, dict[str, ParamData]]  # {instance_id: {symbol: ParamData}}

