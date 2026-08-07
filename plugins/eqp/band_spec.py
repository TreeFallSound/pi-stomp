"""Band specifications for the rkr Parametric EQ (eqp) plugin."""

from __future__ import annotations

from plugins.eq.band_spec import BandSpec
from common.parameter import Symbol

# Every eqp port is a -64..63 integer code, not a physical unit. Width stays in
# codes (q_units="rkr_code" converts it for the curve and readout) so one
# detent moves one code; gain is converted to dB at the port boundary, since
# the curve sums dB and no panel state can carry both.
GAIN_MIN_DB = -30.0
GAIN_MAX_DB = 30.0 * 63.0 / 64.0
CODE_MIN = -64.0
CODE_MAX = 63.0

BAND_SPECS: tuple[BandSpec, ...] = (
    BandSpec("Low", "peak", None, Symbol("LFREQ"), Symbol("LQ"), Symbol("LGAIN"), None,
             20.0, 1000.0, CODE_MIN, CODE_MAX, color=(255, 180, 80),
             gain_min=GAIN_MIN_DB, gain_max=GAIN_MAX_DB, q_units="rkr_code"),
    BandSpec("Mid", "peak", None, Symbol("MFREQ"), Symbol("MQ"), Symbol("MGAIN"), None,
             80.0, 8000.0, CODE_MIN, CODE_MAX, color=(130, 220, 110),
             gain_min=GAIN_MIN_DB, gain_max=GAIN_MAX_DB, q_units="rkr_code"),
    BandSpec("High", "peak", None, Symbol("HFREQ"), Symbol("HQ"), Symbol("HGAIN"), None,
             6000.0, 26000.0, CODE_MIN, CODE_MAX, color=(140, 150, 240),
             gain_min=GAIN_MIN_DB, gain_max=GAIN_MAX_DB, q_units="rkr_code"),
)
