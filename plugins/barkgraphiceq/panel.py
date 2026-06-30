"""Concrete graphic EQ panel for the gx_barkgraphiceq plugin."""

from __future__ import annotations

from plugins.eq.graphic import GraphicEqPanel
from plugins.barkgraphiceq.band_spec import BAND_SPECS


class GxBarkGraphicEqPanel(GraphicEqPanel):
    def build_band_specs(self):
        return BAND_SPECS
