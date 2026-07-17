"""Concrete parametric EQ panel for the rkr Parametric EQ (eqp) plugin."""

from __future__ import annotations

from common.parameter import Symbol
from plugins.eq.parametric import ParametricEqPanel
from plugins.eq.curve import EqState, BandParams
from plugins.eqp.band_spec import BAND_SPECS


class RkrParametricEqPanel(ParametricEqPanel):
    def build_band_specs(self):
        return BAND_SPECS

    def snapshot_state(self) -> EqState:
        params = self.plugin.parameters

        def _val(symbol: Symbol, default: float) -> float:
            p = params.get(symbol)
            return float(p.value) if p is not None else default

        bands: dict[str, BandParams] = {}
        for band in self.bands:
            bands[band.name] = BandParams(
                enabled=True,
                freq=_val(band.freq_sym, 0.5 * (band.freq_min + band.freq_max)),
                q=_val(band.q_sym, 0.7) if band.q_sym is not None else 1.0,
                gain_db=_val(band.gain_sym, 0.0) if band.gain_sym else 0.0,
            )
        return EqState(
            plugin_enabled=not bool(_val(Symbol("BYPASS"), 0.0)),
            global_gain_db=_val(Symbol("GAIN"), 0.0),
            bands=bands,
        )
