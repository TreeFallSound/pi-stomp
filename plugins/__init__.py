"""Plugin panel registry and customization system.

Each panel implementation registers itself against the LV2 URIs it handles.
``lcd320x240.plugin_event`` and ``modhandler.show_fullscreen_panel`` dispatch
via this registry.

This module re-exports the unified customization API from
``plugins.customization`` and keeps the legacy ``PANELS`` dict for
backward compatibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from plugins.customization import (
    PluginCustomization,
    lookup,
    register,
    register_customization,
)

if TYPE_CHECKING:
    from plugins.base import PluginPanel


# Legacy dict — populated by @register_panel / @register decorators at import
# time, same as before.  New code should use ``lookup(plugin)`` instead.
PANELS: dict[str, type[PluginPanel]] = {}


def register_panel(*uris: str):
    """Legacy decorator.  Use ``@register(...)`` instead."""
    return register(*uris)


# Register NAM (Neural Amp Modeler) tile customizations.
# These don't have a panel — just a custom tile class.
from uilib.text import NamPluginTile  # noqa: E402

_NAM_URIS = frozenset(
    {
        "http://github.com/mikeoliphant/neural-amp-modeler-lv2",
        "http://gareus.org/oss/lv2/nam#mono",
        "http://gareus.org/oss/lv2/nam#stereo",
        "https://tone3000.com/plugins/nam",
    }
)

register_customization(*_NAM_URIS, tile_cls=NamPluginTile)


__all__ = [
    "PANELS",
    "PluginCustomization",
    "lookup",
    "register",
    "register_customization",
    "register_panel",
]
