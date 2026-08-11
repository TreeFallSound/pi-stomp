"""Width-port unit handling for the parametric EQ panels.

Calf EQ5 and rkr eqp are the two plugins whose width ports are not bandwidth
in octaves, which is what the curve renderer assumed for years — Calf's are a
true Q, eqp's are rakarrack's -64..63 knob codes. Both are covered here at
several points across their ranges, since a taper bug reads as correct at
whichever single value the fixture happens to pick.

To regenerate snapshots after intentional UI changes:
    uv run pytest tests/v3/test_eq_units.py --snapshot-update
"""

import math

import pytest

from common.parameter import BYPASS_SYMBOL, PortInfo, Parameter, Symbol
from modalapi.plugin import Plugin
from plugins.calf_eq5.band_spec import BAND_SPECS as CALF_SPECS
from plugins.calf_eq5.panel import CalfEq5Panel
from plugins.eq.band_spec import BandSpec
from plugins.eq.curve import BandParams, CurveCache, EqState
from plugins.eq.filters import GRAPH_FREQS, as_bw_oct, as_q, bw_oct_to_q, q_to_bw_oct
from plugins.eq.parametric import band_readout_fields
from plugins.eqp.band_spec import BAND_SPECS as EQP_SPECS
from plugins.eqp.panel import RkrParametricEqPanel
from tests.types import SystemFixture

CALF_URI = "http://calf.sourceforge.net/plugins/Equalizer5Band"
EQP_URI = "http://rakarrack.sourceforge.net/effects.html#eqp"


def _param(
    symbol: str,
    value: float,
    minimum: float,
    maximum: float,
    instance_id: str,
    properties: list[str] | None = None,
) -> Parameter:
    info: PortInfo = {
        "shortName": symbol,
        "symbol": symbol,
        "ranges": {"minimum": minimum, "maximum": maximum},
    }
    if properties is not None:
        info["properties"] = properties
    return Parameter(info, value, None, instance_id)


def _finish(instance_id: str, params: dict[Symbol, Parameter], uri: str) -> Plugin:
    bypass: PortInfo = {"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}
    params[BYPASS_SYMBOL] = Parameter(bypass, False, None, instance_id)
    plugin = Plugin(instance_id, params, {}, "Filter", uri=uri)
    plugin.has_footswitch = False
    plugin.pedalboard_snapshot = {s: float(p.value or 0.0) for s, p in params.items()}
    return plugin


def make_calf_plugin(q: float, instance_id: str = "calf_eq5") -> Plugin:
    """Calf EQ5 with every band active, unity level, and *q* on each width
    port. Levels are linear gain, not dB — that is the port's own unit."""
    params: dict[Symbol, Parameter] = {}
    for b in CALF_SPECS:
        assert b.enable_sym and b.q_sym and b.gain_sym
        params[b.enable_sym] = _param(b.enable_sym, 1.0, 0.0, 5.0, instance_id, ["integer"])
        f0 = 250.0 if b.name == "P1" else (b.freq_min * b.freq_max) ** 0.5
        params[b.freq_sym] = _param(b.freq_sym, f0, b.freq_min, b.freq_max, instance_id, ["logarithmic"])
        params[b.q_sym] = _param(b.q_sym, min(q, b.q_max), b.q_min, b.q_max, instance_id, ["logarithmic"])
        params[b.gain_sym] = _param(b.gain_sym, 2.0, 0.01, 5.0, instance_id, [])
    return _finish(instance_id, params, CALF_URI)


def make_eqp_plugin(code: float, instance_id: str = "eqp") -> Plugin:
    """rkr eqp with *code* on each width port. Every control port is an
    integer -64..63 code; the integer property is what gives the step grid one
    detent per code, so the fixture must carry it."""
    params: dict[Symbol, Parameter] = {}
    params[Symbol("BYPASS")] = _param("BYPASS", 0.0, 0.0, 1.0, instance_id, ["integer", "toggled"])
    params[Symbol("GAIN")] = _param("GAIN", 0.0, -64.0, 63.0, instance_id, ["integer"])
    for b in EQP_SPECS:
        assert b.q_sym and b.gain_sym
        f0 = (b.freq_min * b.freq_max) ** 0.5
        params[b.freq_sym] = _param(b.freq_sym, f0, b.freq_min, b.freq_max, instance_id)
        params[b.q_sym] = _param(b.q_sym, code, -64.0, 63.0, instance_id, ["integer"])
        params[b.gain_sym] = _param(b.gain_sym, 32.0, -64.0, 63.0, instance_id, ["integer"])
    return _finish(instance_id, params, EQP_URI)


def open_panel(v3_system: SystemFixture, plugin: Plugin, panel_cls) -> None:
    handler = v3_system.handler
    assert handler.current
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, v3_system.hw.footswitches)
    handler.lcd.draw_main_panel()
    handler.show_fullscreen_panel(plugin, panel_cls)
    handler.poll_lcd_updates()


# ── conversions ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bw", [0.1, 0.5, 1.0, 2.0, 4.0])
def test_bw_oct_round_trips_through_q(bw: float):
    assert q_to_bw_oct(bw_oct_to_q(bw)) == pytest.approx(bw, rel=1e-6)


def test_octave_bandwidth_ports_never_round_trip():
    """fil4's curve is calibrated on the raw octave value. Passing it through
    Q and back would perturb every fil4 band by the conversion's error."""
    assert as_bw_oct("bw_oct", 0.0625) == 0.0625


def test_calf_q_is_taken_at_face_value():
    """A true-Q port converts to a *narrower* bandwidth as Q rises — the
    inversion this module exists to prevent."""
    assert as_q("q", 4.0) == 4.0
    assert as_bw_oct("q", 10.0) < as_bw_oct("q", 1.0) < as_bw_oct("q", 0.1)


def test_rkr_code_is_geometric_about_its_centre():
    """src/EQ.C:173 — Q = 3 * 30^(code/64), so code 0 is Q 3 and each end is
    a factor of 30 away."""
    assert as_q("rkr_code", 0.0) == pytest.approx(3.0)
    assert as_q("rkr_code", 64.0) == pytest.approx(90.0)
    assert as_q("rkr_code", -64.0) == pytest.approx(0.1)


def test_x42_shelf_slope_matches_upstream():
    """src/lv2.c:280, and iir.h:49-50 clamps the result to [0.25, 2.0] —
    fil4's declared 0.0625..4.0 port lands inside that by construction."""
    assert as_q("x42_shelf_slope", 0.0625) == pytest.approx(0.2129 + 0.0625 / 2.25)
    assert 0.25 <= as_q("x42_shelf_slope", 4.0) <= 2.0


def test_band_spec_rejects_a_width_port_with_no_units():
    """The half-wired flag this replaced defaulted to a silent mis-render."""
    with pytest.raises(ValueError, match="q_units"):
        BandSpec("X", "peak", None, Symbol("f"), Symbol("q"), None, None, 20.0, 20000.0, 0.1, 10.0, color=(0, 0, 0))


# ── curve geometry ───────────────────────────────────────────────────────────


# The graph is 320 points across 20 Hz..20 kHz, so no rendered curve can be
# narrower than this — Calf's top Q decade all lands on one pixel.
GRAPH_RESOLUTION_OCT = math.log2(GRAPH_FREQS[1] / GRAPH_FREQS[0])


def _eq_state(band: BandSpec, p: BandParams) -> EqState:
    return EqState(plugin_enabled=True, global_gain_db=0.0, bands={band.name: p})


def _minus_3db_width_oct(band: BandSpec, p: BandParams) -> float:
    """Width in octaves between the -3 dB-from-peak crossings of one stage."""
    curve = CurveCache().compute([band], _eq_state(band, p))
    above = GRAPH_FREQS[curve >= curve.max() - 3.0]
    return math.log2(above[-1] / above[0])


@pytest.mark.parametrize("q,wider_q", [(0.5, 0.2), (2.0, 0.5), (10.0, 2.0)])
def test_calf_peak_narrows_as_q_rises(q: float, wider_q: float):
    """The reported bug: raising Calf's Q widened the drawn curve."""
    band = next(b for b in CALF_SPECS if b.name == "P1")
    narrow = _minus_3db_width_oct(band, BandParams(True, 1000.0, q, 12.0))
    wide = _minus_3db_width_oct(band, BandParams(True, 1000.0, wider_q, 12.0))
    assert narrow < wide


def test_calf_peak_at_max_q_is_a_spike_not_a_shelf():
    """Q 100 is finer than one graph pixel. Under the octaves reading it was
    100 *octaves* wide — the whole plot — so pinning it to the floor is the
    regression guard the monotonic test can't give at this end of the range."""
    band = next(b for b in CALF_SPECS if b.name == "P1")
    width = _minus_3db_width_oct(band, BandParams(True, 1000.0, 100.0, 12.0))
    assert width <= GRAPH_RESOLUTION_OCT


def test_calf_q_readout_matches_the_port():
    """MOD-UI shows the port value; so must we, on peaks and shelves alike.
    The shelves used to borrow x42's slope mapping and print 0.707 as 0.53."""
    for name in ("P1", "LS", "HS"):
        band = next(b for b in CALF_SPECS if b.name == name)
        _, _, q, _ = band_readout_fields(band, BandParams(True, 1000.0, 0.707, 6.0))
        assert q == "Q 0.71"


def test_eqp_readout_decodes_the_knob_code():
    band = EQP_SPECS[0]
    _, _, q, _ = band_readout_fields(band, BandParams(True, 500.0, 0.0, 6.0))
    assert q == "Q 3.00"


# ── panel sagas ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("q", [0.1, 0.707, 4.0, 100.0])
def test_calf_eq5_renders_across_q_range(v3_system: SystemFixture, snapshot, q: float):
    """Calf's Q spans three decades; a taper bug hides at any single value."""
    open_panel(v3_system, make_calf_plugin(q), CalfEq5Panel)
    snapshot(f"q_{q}")


@pytest.mark.parametrize("code", [-64.0, -32.0, 0.0, 32.0, 63.0])
def test_eqp_renders_across_code_range(v3_system: SystemFixture, snapshot, code: float):
    open_panel(v3_system, make_eqp_plugin(code), RkrParametricEqPanel)
    snapshot(f"code_{int(code)}")


def test_eqp_tweak_writes_back_integer_codes(v3_system: SystemFixture, snapshot):
    """Width stays in codes end to end, so a detent moves exactly one; gain
    converts at the port boundary and must land back on the integer grid."""
    from pistomp.controller import Controller
    from pistomp.input.event import EncoderEvent

    class _Enc(Controller):
        def __init__(self, id: int):
            super().__init__(midi_channel=0, midi_CC=None)
            self.id = id

    handler = v3_system.handler
    plugin = make_eqp_plugin(0.0)
    open_panel(v3_system, plugin, RkrParametricEqPanel)
    snapshot("centred")

    for _ in range(20):
        handler.handle(EncoderEvent(controller=_Enc(3), rotations=1))
    handler.poll_lcd_updates()
    snapshot("narrowed")

    for _ in range(10):
        handler.handle(EncoderEvent(controller=_Enc(1), rotations=-1))
    handler.poll_lcd_updates()
    snapshot("cut")

    sent_q = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "LQ")
    sent_gain = v3_system.ws_bridge.sent_values_for(plugin.instance_id, "LGAIN")
    assert sent_q and sent_q[-1] == 20.0
    assert sent_gain and all(v == int(v) for v in sent_gain)
    assert -64.0 <= sent_gain[-1] < 32.0
