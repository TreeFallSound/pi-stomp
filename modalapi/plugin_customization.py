"""Per-plugin-type customization — the *type*, not the registry.

This lives in ``modalapi`` (below ``plugins``) so ``Plugin`` and ``Pedalboard``
can name the type without importing the ``plugins`` package. Concrete
customizations and the URI registry live up in ``plugins.customization``; the
composition root (the handler) injects a resolver downward. ``modalapi`` never
reaches up into ``plugins``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeVar

from common.color import RectBorder

if TYPE_CHECKING:
    from modalapi.plugin import Plugin
    from plugins.base import PluginPanel
    from uilib.widget import Widget


@dataclass(frozen=True)
class PluginExtraData:
    """Base for per-instance parsed plugin data.

    Plugin types subclass this with their own typed fields (see
    ``NamData``/``NotesData``). The registry is keyed by a runtime URI, so the
    type is erased to this base at the lookup boundary; consumers recover their
    concrete type with ``extra_data_as`` (a checked narrowing, not a cast).
    """


_TExtra = TypeVar("_TExtra", bound=PluginExtraData)


def extra_data_as(plugin: Plugin, kind: type[_TExtra]) -> _TExtra | None:
    """Return ``plugin.extra_data`` if it is a ``kind``, else ``None``.

    One runtime-checked narrowing for all consumers — replaces repeated
    ``isinstance`` guards while staying fully type-safe (no ``Any``, no cast).
    """
    data = plugin.extra_data
    return data if isinstance(data, kind) else None


@dataclass(frozen=True)
class PluginCustomization:
    """All per-plugin-type overrides for a single LV2 URI.

    Every field defaults to ``None``/``False``: an unregistered plugin gets a
    bare ``PluginCustomization()`` meaning "standard heuristic behaviour".
    """

    panel_cls: type[PluginPanel] | None = None
    menu_widget_cls: type[Widget] | None = None
    display_name: str | None = None
    display_name_fn: Callable[[Plugin], str | None] | None = field(default=None, compare=False, hash=False)
    subtitle_fn: Callable[[Plugin], str | None] | None = field(default=None, compare=False, hash=False)
    intercept_shortpress: bool = False
    tile_active_color: tuple[int, int, int] | None = None
    tile_border: RectBorder | None = None
    extra_data_fn: Callable[[str, int], PluginExtraData | None] | None = field(default=None, compare=False, hash=False)


# A resolver from URI to customization. The registry's ``lookup`` satisfies it;
# ``Pedalboard`` accepts one so it never imports the registry directly.
Customizer = Callable[["str | None"], PluginCustomization]

_DEFAULT = PluginCustomization()


def default_customizer(uri: str | None) -> PluginCustomization:  # noqa: ARG001
    """No-op resolver: every URI gets default behaviour. Used when no registry
    is injected (v1 handler, headless tools, direct construction)."""
    return _DEFAULT
