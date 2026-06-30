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
import plugins.eq.parametric   # noqa: F401  # ParametricEqPanel (ABC) + GraphWidget etc.
import plugins.eq.graphic      # noqa: F401  # GraphicEqPanel (ABC) + BarWidget
import plugins.fil4            # noqa: F401
import plugins.nam             # noqa: F401
import plugins.notes.panel     # noqa: F401
import plugins.distaq          # noqa: F401
import plugins.zameq2          # noqa: F401
import plugins.tapeq           # noqa: F401
import plugins.tapeqbw         # noqa: F401
import plugins.capseq10        # noqa: F401
import plugins.capseq10x2      # noqa: F401
import plugins.graphiceq       # noqa: F401
import plugins.barkgraphiceq   # noqa: F401
import plugins.zamgeq31        # noqa: F401
import plugins.three_band_eq   # noqa: F401
import plugins.three_band_splitter  # noqa: F401
import plugins.mdamultiband    # noqa: F401
import plugins.mdabandisto     # noqa: F401
import plugins.multiband_menu  # noqa: F401  # CustomMenuWidget base

__all__ = [
    "PluginCustomization",
    "lookup",
    "register",
    "registered_uris",
]
