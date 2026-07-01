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
class PluginCustomization:
    panel_cls: type[PluginPanel] | None = None
    display_name: str | None = None
    display_name_fn: Callable[[Plugin], str | None] | None = field(default=None, compare=False, hash=False)
    subtitle_fn: Callable[[Plugin], str | None] | None = field(default=None, compare=False, hash=False)
    intercept_shortpress: bool = False
    tile_active_color: tuple[int, int, int] | None = None
    tile_border: RectBorder | None = None
    extra_data: PluginExtraData | None = None


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
