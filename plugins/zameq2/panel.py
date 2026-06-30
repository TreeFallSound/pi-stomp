"""Concrete parametric EQ panel for the ZamEQ2 plugin."""

from __future__ import annotations

from plugins.eq.parametric import ParametricEqPanel
from plugins.zameq2.band_spec import BAND_SPECS


class ZamEQ2Panel(ParametricEqPanel):
    def build_band_specs(self):
        return BAND_SPECS
