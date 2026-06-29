"""NAM (Neural Amp Modeler) plugin customizations.

Registers custom tile colors and border for NAM plugin URIs.
A fullscreen panel will be added here in a future change.
"""

from __future__ import annotations

from common.color import RectBorder
from plugins.customization import PluginCustomization, register

_NAM_YELLOW = (224, 179, 0)
_NAM_RED = (220, 20, 20)
_NAM_BLUE = (20, 30, 220)

_NAM_URIS = (
    "http://github.com/mikeoliphant/neural-amp-modeler-lv2",
    "http://gareus.org/oss/lv2/nam#mono",
    "http://gareus.org/oss/lv2/nam#stereo",
    "https://tone3000.com/plugins/nam",
)

register(
    *_NAM_URIS,
    customization=PluginCustomization(
        tile_active_color=_NAM_YELLOW,
        tile_border=RectBorder(
            top=_NAM_RED,
            right=_NAM_YELLOW,
            bottom=_NAM_BLUE,
            left=_NAM_YELLOW,
        ),
    ),
)
