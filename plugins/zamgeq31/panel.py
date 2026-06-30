"""Concrete graphic EQ panel for the ZamGEQ31 plugin."""

from __future__ import annotations

from plugins.eq.graphic import GraphicEqPanel
from plugins.zamgeq31.band_spec import BAND_SPECS


class ZamGEQ31Panel(GraphicEqPanel):
    def build_band_specs(self):
        return BAND_SPECS
