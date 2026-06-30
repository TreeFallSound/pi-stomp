"""Concrete parametric EQ panel for the TAP EQ plugin."""

from __future__ import annotations

from plugins.eq.parametric import ParametricEqPanel
from plugins.tapeq.band_spec import BAND_SPECS


class TapEqPanel(ParametricEqPanel):
    def build_band_specs(self):
        return BAND_SPECS
