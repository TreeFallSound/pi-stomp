"""Concrete parametric EQ panel for the TAP EQ/BW plugin."""

from __future__ import annotations

from plugins.eq.parametric import ParametricEqPanel
from plugins.tapeqbw.band_spec import BAND_SPECS


class TapEqBwPanel(ParametricEqPanel):
    def build_band_specs(self):
        return BAND_SPECS
