"""ZamComp: reuses the a-comp panel — its LV2 ports (thr/rat/kn/mak) match exactly."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.zamcomp.panel import ZamCompPanel

ZAMCOMP_URI = "urn:zamaudio:ZamComp"

register(
    ZAMCOMP_URI,
    customization=PluginCustomization(
        panel_cls=ZamCompPanel,
        display_name="ZamComp",
    ),
)
