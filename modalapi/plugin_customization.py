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

"""Per-plugin-type customization type. The registry lives in `plugins.customization`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, TypeVar

from common.color import RectBorder
from common.param_roles import ParamRole
from common.parameter import Symbol

if TYPE_CHECKING:
    from common.parameter import Parameter
    from modalapi.plugin import Plugin
    from plugins.base import PluginPanel


@dataclass(frozen=True)
class PluginExtraData:
    """Base for per-instance plugin data. Subclass and narrow with `extra_data_as`."""


_TExtra = TypeVar("_TExtra", bound=PluginExtraData)


def extra_data_as(plugin: Plugin, kind: type[_TExtra]) -> _TExtra | None:
    """Type-safe narrowing of `plugin.extra_data` to `kind`."""
    data = plugin.extra_data
    return data if isinstance(data, kind) else None


@dataclass(frozen=True)
class LedSpec:
    """Declarative footswitch-LED rendering for a plugin, keyed off its own
    (generically-mirrored) output ports. Interpreted by the handler's generic
    LED driver — no per-plugin imperative code required.

    state_symbol: the output port whose integer value selects `colors`.
    downbeat_symbol: an optional second output port (e.g. loopjefe's
      `measure_number`) whose value == 0 means "this is the loop's own
      downbeat" — brightens the color by `downbeat_tint` per channel.
    off_states / steady_states: state values that render as off, or as a
      steady (non-pulsing) color even when `pulse` is True.
    """

    state_symbol: str
    colors: dict[int, tuple[int, int, int]]
    pulse: bool = False
    off_states: frozenset[int] = frozenset()
    steady_states: frozenset[int] = frozenset()
    downbeat_symbol: str | None = None
    downbeat_tint: int = 60


@dataclass(frozen=True)
class PinnedParam:
    """One arc-ring slot in a parameter window.

    Color is derived from the parameter's unit at render time, not stored here.
    """

    symbol: Symbol
    label: str
    # value -> (value_text, unit_text); unit "" ⇒ single centred line, non-empty
    # ⇒ unit stacked on a second line (same contract as arc_dial.DialFormatter).
    display_fn: Callable[[float], tuple[str, str]] | None = None


@dataclass(frozen=True)
class PluginCustomization:
    panel_cls: type[PluginPanel] | None = None
    display_name: str | None = None
    display_name_fn: Callable[[Plugin], str | None] | None = field(default=None, compare=False, hash=False)
    subtitle_fn: Callable[[Plugin], str | None] | None = field(default=None, compare=False, hash=False)
    intercept_shortpress: bool = False
    tile_active_color: tuple[int, int, int] | None = None
    tile_border: RectBorder | None = None
    extra_data: PluginExtraData | None = None
    led_spec: LedSpec | None = None

    # Per-symbol edit-math classification, supplementing the LV2 port's
    #  Symbols absent here are ParamRole.GENERIC.
    param_roles: dict[Symbol, ParamRole] = field(default_factory=dict, compare=False, hash=False)

    # Arc-ring slots pinned to the top of the parameter window. When set, these
    # replace the heuristic (first N continuous params). None = use heuristic.
    pinned_params: tuple[PinnedParam, ...] | None = None

    # Redundant ports the UI must never paint: author-rolled bypass/enable ports
    # carrying no LV2 metadata to catch them. `common.parameter.is_hidden_port`
    # handles the ones that do.
    hidden_params: frozenset[Symbol] = frozenset()

    # Live label for a bound control (knob/footswitch/dialog title).
    control_label_fn: Callable[[Parameter], str] | None = field(default=None, compare=False, hash=False)


class Customizer(Protocol):
    """Resolver signature used by `Pedalboard`. Always takes `uri`; the
    bundle + instance args are only needed to populate `extra_data`, so
    they have defaults for call sites that don't have that context
    (dynamic plugin adds, headless tools, tests)."""

    def __call__(
        self,
        uri: str | None,
        bundlepath: str = "",
        instance_number: int | None = None,
    ) -> PluginCustomization: ...


def default_customizer(
    uri: str | None,  # noqa: ARG001
    bundlepath: str = "",  # noqa: ARG001
    instance_number: int | None = None,  # noqa: ARG001
) -> PluginCustomization:
    return PluginCustomization()
