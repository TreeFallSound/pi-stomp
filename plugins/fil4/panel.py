"""Concrete parametric EQ panel for the fil4 / x42-eq plugin."""

from __future__ import annotations

from plugins.eq.parametric import ParametricEqPanel
from plugins.fil4.band_spec import BAND_SPECS


class Fil4Panel(ParametricEqPanel):
    """Full-screen panel for editing an x42-eq (fil4) instance."""

    _show_axis_labels: bool = False

    def build_band_specs(self):
        return BAND_SPECS
