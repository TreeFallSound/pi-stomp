"""Concrete graphic EQ panel for the caps-Eq10 plugin."""

from __future__ import annotations

from plugins.eq.graphic import GraphicEqPanel
from plugins.capseq10.band_spec import BAND_SPECS


class CapsEq10Panel(GraphicEqPanel):
    def build_band_specs(self):
        return BAND_SPECS
