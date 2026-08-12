# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Concrete parametric EQ panel for the rkr Parametric EQ (eqp) plugin."""

from __future__ import annotations

import math

from common.parameter import Symbol
from plugins.eq.parametric import ParametricEqPanel
from plugins.eq.curve import EqState, BandParams
from plugins.eq.band_spec import BandSpec
from plugins.eqp.band_spec import BAND_SPECS

# rakarrack works in 0..127 knob codes; the LV2 wrapper subtracts 64 to expose
# them as -64..63 and adds it back before every changepar (lv2/rkrlv2.C:1349).
_CODE_OFFSET = 64.0

# Band gain: src/EQ.C:167.
_GAIN_DB_PER_CODE = 30.0 / 64.0

# Output volume: src/EQ.C:110 — a gain curve, not a dB code, and its unity
# point is nowhere near 0. Range is 0.05..10.0 linear (-26..+20 dB).
_VOLUME_FLOOR = 0.005
_VOLUME_SCALE = 10.0


def _band_gain_db(code: float) -> float:
    return code * _GAIN_DB_PER_CODE


def _band_gain_code(db: float) -> float:
    return round(db / _GAIN_DB_PER_CODE)


def _volume_db(code: float) -> float:
    linear = _VOLUME_SCALE * _VOLUME_FLOOR ** (1.0 - (code + _CODE_OFFSET) / 127.0)
    return 20.0 * math.log10(linear)


class RkrParametricEqPanel(ParametricEqPanel):
    def build_band_specs(self):
        return BAND_SPECS

    def _port_value_for_band_param(self, band: BandSpec, field_name: str, value: float) -> float:
        if field_name == "gain_db":
            return _band_gain_code(value)
        return value

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
                q=_val(band.q_sym, 0.0) if band.q_sym is not None else 1.0,
                gain_db=_band_gain_db(_val(band.gain_sym, 0.0)) if band.gain_sym else 0.0,
            )
        return EqState(
            plugin_enabled=not bool(_val(Symbol("BYPASS"), 0.0)),
            global_gain_db=_volume_db(_val(Symbol("GAIN"), 0.0)),
            bands=bands,
        )
