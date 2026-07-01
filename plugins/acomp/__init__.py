"""DISTRHO a-comp compressor: windowed panel with a live gain-reduction meter."""

from __future__ import annotations

from plugins.acomp.panel import AcompWindow
from plugins.customization import PluginCustomization, register

ACOMP_URI = "urn:distrho:a-comp"

register(
    ACOMP_URI,
    customization=PluginCustomization(
        panel_cls=AcompWindow,
        display_name="DISTRHO Compressor",
    ),
)
