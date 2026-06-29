"""Plugin customization registry.

A single source of truth for all per-plugin-type overrides.  Each LV2 URI
(or URI prefix) can register a ``PluginCustomization`` dataclass that bundles:

1. **Panel** — a fullscreen ``PluginPanel`` subclass for this plugin type.
2. **Tile class** — a custom ``PluginTile`` subclass for the plugin grid.
3. **Display name** — override the heuristic name.
4. **Shortpress** — whether a short click opens the panel (like longpress)
   instead of toggling bypass.

Future customizations (subtitles, color schemes, …) are just new fields on
the dataclass — no existing registrations break.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plugins.base import PluginPanel
    from uilib.text import PluginTile


@dataclass(frozen=True)
class PluginCustomization:
    """All per-plugin-type overrides for a single LV2 URI (or URI family).

    Every field has a sensible default — unregistered plugins get a
    ``PluginCustomization()`` with all ``None`` / ``False``, which means
    "use the standard heuristic behaviour".
    """

    # 1. Fullscreen panel class (None → generic parameter menu on long-click)
    panel_cls: type[PluginPanel] | None = None

    # 2. Custom tile class (None → standard PluginTile)
    tile_cls: type[PluginTile] | None = None

    # 3. Override display name (None → Plugin.display_name heuristic)
    display_name: str | None = None

    # 4. Shortpress opens the panel instead of toggling bypass
    intercept_shortpress: bool = False


# ── Registry ──────────────────────────────────────────────────────────────────

# Exact URI match (fast path)
_URI_MAP: dict[str, PluginCustomization] = {}

# URI prefix match (e.g. "http://gareus.org/oss/lv2/nam" matches nam#mono)
_PREFIX_MAP: list[tuple[str, PluginCustomization]] = []

# Category fallback (e.g. all "Delay" plugins)
_CATEGORY_MAP: dict[str, PluginCustomization] = {}

_DEFAULT = PluginCustomization()


def register(*uris: str, prefix: str | None = None, category: str | None = None, **overrides):
    """Decorator that registers a panel class and/or customization overrides.

    Usage — panel only (backward compatible with ``@register_panel``)::

        @register("http://gareus.org/oss/lv2/fil4#mono")
        class EqPanel(PluginPanel): ...

    Usage — full customization::

        @register("http://example.com/nam#mono", prefix="http://example.com/nam",
                  tile_cls=NamPluginTile, intercept_shortpress=True)
        class NamPanel(PluginPanel): ...
    """
    customization = PluginCustomization(**overrides)

    def decorator(cls):
        nonlocal customization
        if overrides:
            object.__setattr__(customization, "panel_cls", cls)
        else:
            # Read intercept_shortpress from the class if not explicitly passed
            sp = getattr(cls, "intercept_shortpress", False)
            customization = PluginCustomization(panel_cls=cls, intercept_shortpress=sp)
        _do_register(uris, prefix, category, customization)
        return cls

    return decorator


def register_customization(*uris: str, prefix: str | None = None, category: str | None = None, **overrides) -> None:
    """Register customizations without a panel class (bare function call)."""
    customization = PluginCustomization(**overrides)
    _do_register(uris, prefix, category, customization)


def _do_register(
    uris: tuple[str, ...],
    prefix: str | None,
    category: str | None,
    customization: PluginCustomization,
) -> None:
    for u in uris:
        _URI_MAP[u] = customization
    if prefix is not None:
        _PREFIX_MAP.append((prefix, customization))
    if category is not None:
        _CATEGORY_MAP[category] = customization


def lookup(plugin) -> PluginCustomization:
    """Resolve the customization for a plugin.

    *plugin* can be a ``Plugin`` instance or a plain URI string (for testing).
    Priority: exact URI → URI prefix → category → default (no overrides).
    """
    if isinstance(plugin, str):
        uri = plugin
        category = None
    else:
        uri = getattr(plugin, "uri", None)
        category = getattr(plugin, "category", None)

    if uri is not None and uri in _URI_MAP:
        return _URI_MAP[uri]

    if uri is not None:
        for pattern, c in _PREFIX_MAP:
            if uri.startswith(pattern):
                return c

    if category is not None and category in _CATEGORY_MAP:
        return _CATEGORY_MAP[category]

    return _DEFAULT
