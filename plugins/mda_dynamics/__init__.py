"""MDA Dynamics: full-screen panel with live GR meter."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.mda_dynamics.panel import MdaDynamicsPanel

MDA_DYNAMICS_URI = "http://moddevices.com/plugins/mda/Dynamics"

register(
    MDA_DYNAMICS_URI,
    customization=PluginCustomization(
        panel_cls=MdaDynamicsPanel,
        display_name="MDA Dynamics",
    ),
)
