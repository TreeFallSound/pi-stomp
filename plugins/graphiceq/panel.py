"""Concrete graphic EQ panel for the gx_graphiceq plugin."""

from __future__ import annotations

from plugins.eq.graphic import GraphicEqPanel
from plugins.graphiceq.band_spec import BAND_SPECS


class GxGraphicEqPanel(GraphicEqPanel):
    def build_band_specs(self):
        return BAND_SPECS
