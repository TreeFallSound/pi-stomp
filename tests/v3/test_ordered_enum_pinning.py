"""Ordered integer enums (Filter Order, Compressor Mode) pin as arc rings.

An enumeration whose scale points are a contiguous ascending integer ramp reads
as a magnitude, not a categorical pick — so the pin heuristic should treat it
like a continuous param, and the ring should show the scale-point label.
"""

from __future__ import annotations

from common.parameter import Parameter, PortInfo, Symbol, Type
from modalapi.plugin import Plugin
from plugins.parameter_window import ParameterWindow


def _enum(symbol: str, minimum: float, maximum: float, points: list[tuple[str, float]]) -> Parameter:
    info: PortInfo = {
        "symbol": symbol,
        "shortName": symbol,
        "ranges": {"minimum": minimum, "maximum": maximum},
        "properties": ["enumeration", "integer"],
        "scalePoints": [{"label": lbl, "value": val} for lbl, val in points],
    }
    return Parameter(info, minimum, None, "P")


def _cont(symbol: str) -> Parameter:
    info: PortInfo = {"symbol": symbol, "shortName": symbol, "ranges": {"minimum": 0.0, "maximum": 1.0}}
    return Parameter(info, 0.0, None, "P")


# ── the predicate ──────────────────────────────────────────────────────────

def test_filter_order_is_ordered_enum():
    # mod-lpf Order: values 0/1/2, labels "1"/"2"/"3".
    order = _enum("Order", 0, 2, [("1", 0), ("2", 1), ("3", 2)])
    assert order.type == Type.ENUMERATION
    assert order.is_ordered_enum()


def test_comp_mode_is_ordered_enum():
    # System-Compressor COMP_MODE: values 1/2/3, word labels.
    mode = _enum("COMP_MODE", 1, 3, [("Light Comp", 1), ("Mild Comp", 2), ("Heavy Comp", 3)])
    assert mode.is_ordered_enum()


def test_non_contiguous_enum_is_not_ordered():
    # MIDI-CC-style enum: gaps between values → not a level.
    e = _enum("cc", 0, 127, [("off", 0), ("low", 7), ("high", 64)])
    assert not e.is_ordered_enum()


def test_continuous_param_is_not_ordered_enum():
    assert not _cont("Freq").is_ordered_enum()


# ── the heuristic ──────────────────────────────────────────────────────────

def _window(params: dict[Symbol, Parameter]) -> ParameterWindow:
    plugin = Plugin("P", params, {}, "Filter")
    win = ParameterWindow.__new__(ParameterWindow)
    win.plugin = plugin
    return win


def test_heuristic_pins_ordered_enum():
    params = {
        Symbol("Order"): _enum("Order", 0, 2, [("1", 0), ("2", 1), ("3", 2)]),
    }
    slots = _window(params)._heuristic_slots()
    symbols = [s.symbol for s in slots]
    assert Symbol("Order") in symbols


def test_heuristic_pins_contiguous_word_label_enum():
    # A contiguous ramp pins even with word labels; the ring shows the label.
    params = {
        Symbol("mode"): _enum("mode", 0, 2, [("Bypass", 0), ("Warm", 1), ("Bright", 2)]),
    }
    (slot,) = _window(params)._heuristic_slots()
    assert slot.symbol == Symbol("mode")
    assert slot.display_fn is not None
    assert slot.display_fn(1.0) == ("Warm", "")


def test_heuristic_skips_categorical_enum():
    params = {
        Symbol("Shape"): _enum("Shape", 0, 2, [("Sine", 0), ("Square", 7), ("Saw", 42)]),
    }
    slots = _window(params)._heuristic_slots()
    assert slots == []


def test_pinned_ordered_enum_shows_scalepoint_label():
    params = {Symbol("Order"): _enum("Order", 0, 2, [("1", 0), ("2", 1), ("3", 2)])}
    (slot,) = _window(params)._heuristic_slots()
    assert slot.display_fn is not None
    assert slot.display_fn(0.0) == ("1", "")
    assert slot.display_fn(2.0) == ("3", "")


# ── toggles ────────────────────────────────────────────────────────────────

def _toggle(symbol: str) -> Parameter:
    info: PortInfo = {"symbol": symbol, "shortName": symbol, "ranges": {"minimum": 0.0, "maximum": 1.0}, "properties": ["toggled"]}
    return Parameter(info, 0.0, None, "P")


def test_heuristic_pins_toggle():
    (slot,) = _window({Symbol("boost"): _toggle("boost")})._heuristic_slots()
    assert slot.symbol == Symbol("boost")


def test_pinned_toggle_shows_on_off():
    (slot,) = _window({Symbol("boost"): _toggle("boost")})._heuristic_slots()
    assert slot.display_fn is not None
    assert slot.display_fn(0.0) == ("Off", "")
    assert slot.display_fn(1.0) == ("On", "")


def test_toggle_ring_is_ms_green():
    from uilib.misc import _UNIT_COLORS, color_for_param
    assert color_for_param(_toggle("boost")) == _UNIT_COLORS["ms"]
