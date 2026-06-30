"""Concrete parametric EQ panel for the DISTRHO Audio EQ plugin."""

from __future__ import annotations

from plugins.eq.parametric import ParametricEqPanel
from plugins.distaq.band_spec import BAND_SPECS


class DistrhoAEqPanel(ParametricEqPanel):
    def build_band_specs(self):
        return BAND_SPECS
