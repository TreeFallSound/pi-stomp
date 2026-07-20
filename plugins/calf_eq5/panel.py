from __future__ import annotations

import math

from plugins.eq.parametric import ParametricEqPanel
from plugins.calf_eq5.band_spec import BAND_SPECS
from common.parameter import Symbol
from plugins.eq.curve import BandParams, EqState
from plugins.eq.band_spec import BandSpec


def _linear_to_db(lin: float) -> float:
    if lin <= 0.0:
        return -40.0
    return 20.0 * math.log10(lin)


def _db_to_linear(db: float) -> float:
    return 10.0 ** (db / 20.0)


class CalfEq5Panel(ParametricEqPanel):
    def build_band_specs(self):
        return BAND_SPECS

    def _port_value_for_band_param(self, band: BandSpec, field_name: str, value: float) -> float:
        if field_name == "gain_db":
            return _db_to_linear(value)
        return value

    def snapshot_state(self) -> EqState:
        params = self.plugin.parameters

        def _val(symbol: Symbol, default: float) -> float:
            p = params.get(symbol)
            return float(p.value) if p is not None else default

        bands: dict[str, BandParams] = {}
        for band in self.bands:
            enable_val = _val(band.enable_sym, 0.0) if band.enable_sym is not None else 1.0
            lin_gain = _val(band.gain_sym, 1.0) if band.gain_sym else 1.0
            bands[band.name] = BandParams(
                enabled=bool(enable_val),
                freq=_val(band.freq_sym, 0.5 * (band.freq_min + band.freq_max)),
                q=_val(band.q_sym, 0.707) if band.q_sym is not None else 1.0,
                gain_db=_linear_to_db(lin_gain) if band.gain_sym else 0.0,
            )
        return EqState(
            plugin_enabled=bool(_val(Symbol("enable"), 1.0)),
            global_gain_db=_val(Symbol("gain"), 0.0),
            bands=bands,
        )
