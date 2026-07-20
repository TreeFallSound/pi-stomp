"""Per-plugin-type customization type. The registry lives in `plugins.customization`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, TypeVar

from common.color import RectBorder

if TYPE_CHECKING:
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
