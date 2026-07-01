"""DISTRHO a-comp compressor: full-screen panel with a live gain-reduction meter."""

from __future__ import annotations

from plugins.acomp.panel import AcompPanel
from plugins.customization import PluginCustomization, register

ACOMP_URI = "urn:distrho:a-comp"

register(
    ACOMP_URI,
    customization=PluginCustomization(
        panel_cls=AcompPanel,
        display_name="DISTRHO Compressor",
    ),
)
