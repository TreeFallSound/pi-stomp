"""Plugin panel registry and customization system.

Each panel implementation registers itself against the LV2 URIs it handles.
``lcd320x240.plugin_event`` and ``modhandler.show_fullscreen_panel`` dispatch
via this registry.

This module re-exports the unified customization API from
``plugins.customization`` and triggers all panel registrations at import time.
"""

from __future__ import annotations

from plugins.customization import (
    PluginCustomization,
    lookup,
    register,
    registered_uris,
)

# Import all panel/customization modules to trigger their registrations.
import plugins.eq.panel      # noqa: F401
import plugins.nam           # noqa: F401
import plugins.notes.panel   # noqa: F401


__all__ = [
    "PluginCustomization",
    "lookup",
    "register",
    "registered_uris",
]
