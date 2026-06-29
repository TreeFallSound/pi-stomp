"""Plugin customization registry.

A single source of truth for all per-plugin-type overrides.  Each LV2 URI
can register a ``PluginCustomization`` dataclass that bundles:

1. **Panel** — a fullscreen ``PluginPanel`` subclass for this plugin type.
2. **Display name** — override the heuristic name (static string or callable).
3. **Subtitle** — override the subtitle shown below the plugin name.
4. **Shortpress** — whether a short click opens the panel (like longpress)
   instead of toggling bypass.
5. **Tile active color** — background color when the plugin is active.
6. **Tile border** — per-side border colors for the plugin tile.

Future customizations (color schemes, …) are just new fields on
the dataclass — no existing registrations break.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from common.color import RectBorder

if TYPE_CHECKING:
    from plugins.base import PluginPanel
    from modalapi.plugin import Plugin


@dataclass(frozen=True)
class PluginCustomization:
    """All per-plugin-type overrides for a single LV2 URI.

    Every field has a sensible default — unregistered plugins get a
    ``PluginCustomization()`` with all ``None`` / ``False``, which means
    "use the standard heuristic behaviour".
    """

    panel_cls: type[PluginPanel] | None = None
    display_name: str | None = None
    display_name_fn: Callable[[Plugin], str | None] | None = field(default=None, compare=False, hash=False)
    subtitle_fn: Callable[[Plugin], str | None] | None = field(default=None, compare=False, hash=False)
    intercept_shortpress: bool = False
    tile_active_color: tuple[int, int, int] | None = None
    tile_border: RectBorder | None = None


# ── Registry ──────────────────────────────────────────────────────────────────

_URI_MAP: dict[str, PluginCustomization] = {}
_DEFAULT = PluginCustomization()


def register(*uris: str, customization: PluginCustomization) -> None:
    """Register a ``PluginCustomization`` for one or more LV2 URIs."""
    for uri in uris:
        _URI_MAP[uri] = customization


def lookup(plugin: Plugin) -> PluginCustomization:
    """Resolve the customization for a plugin by its URI.

    Returns ``PluginCustomization()`` (all defaults) for unregistered URIs.
    """
    if not plugin.uri:
        return _DEFAULT

    c = _URI_MAP.get(plugin.uri)
    return c if c is not None else _DEFAULT


def registered_uris() -> frozenset[str]:
    """Return all URIs that have a registered customization."""
    return frozenset(_URI_MAP)
