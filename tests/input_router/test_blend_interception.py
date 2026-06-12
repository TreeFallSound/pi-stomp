"""Blend mode interception at the handler level.

Verifies that BlendMode.intercept() and InputController.handle_event()
correctly consume events from the blend input and reject all others.
"""

from unittest.mock import MagicMock

from blend.easing import EASING_FUNCTIONS
from blend.input_controller import InputController
from blend.manager import BlendMode
from blend.parameter_setter import ParameterSetter
from blend.stop import BlendStop
from pistomp.input.event import AnalogEvent, EncoderEvent, SwitchEvent, SwitchEventKind
from pistomp.encoder_controller import EncoderController


def _make_encoder(midi_CC=70, midi_channel=0, id_=1):
    enc = EncoderController(
        d_pin=None,
        clk_pin=None,
        midi_CC=midi_CC,
        midi_channel=midi_channel,
        id=id_,
    )
    return enc


def _make_ic(enc):
    """Minimal InputController wired to a single stop (no interpolation needed)."""
    setter = MagicMock(spec=ParameterSetter)
    setter.send_parameter.return_value = True

    stop = BlendStop(
        position=0.0,
        snapshot_index=0,
        snapshot_state={"FX": {"Level": 0.5}},
    )
    ic = InputController(
        easing_func=EASING_FUNCTIONS["linear"],
        stops=[stop, stop],
        segment_diff_maps=[{"FX": {}}],
        parameter_setter=setter,
    )
    ic.attach_to_input(enc)
    return ic, setter


# ---------------------------------------------------------------------------
# InputController.handle_event
# ---------------------------------------------------------------------------


def test_handle_event_consumes_event_from_attached_encoder():
    enc = _make_encoder()
    ic, setter = _make_ic(enc)

    consumed = ic.handle_event(EncoderEvent(controller=enc, rotations=1))

    assert consumed is True


def test_handle_event_rejects_event_from_other_encoder():
    enc1 = _make_encoder(id_=1)
    enc2 = _make_encoder(id_=2)
    ic, _ = _make_ic(enc1)

    consumed = ic.handle_event(EncoderEvent(controller=enc2, rotations=1))

    assert consumed is False


def test_handle_event_rejects_analog_event_from_wrong_controller():
    enc = _make_encoder(id_=1)
    ic, _ = _make_ic(enc)
    other = MagicMock()
    other.id = 99

    consumed = ic.handle_event(AnalogEvent(controller=other, raw_value=512, midi_value=64))

    assert consumed is False


def test_handle_event_rejects_switch_event_even_if_same_id():
    """SwitchEvents are never blend inputs — the controller identity check alone isn't enough."""
    enc = _make_encoder(id_=1)
    ic, _ = _make_ic(enc)

    consumed = ic.handle_event(SwitchEvent(controller=enc, kind=SwitchEventKind.PRESS))

    assert consumed is False


# ---------------------------------------------------------------------------
# BlendMode.intercept delegation
# ---------------------------------------------------------------------------


def test_blend_mode_intercept_delegates_to_input_controller():
    enc = _make_encoder(id_=1)
    ic, _ = _make_ic(enc)
    bm = BlendMode(MagicMock(), {"name": "Test", "input_id": 1})  # type: ignore[arg-type]
    bm.input_controller = ic

    consumed = bm.intercept(EncoderEvent(controller=enc, rotations=1))

    assert consumed is True


def test_blend_mode_intercept_no_controller_returns_false():
    bm = BlendMode(MagicMock(), {"name": "Test", "input_id": 1})  # type: ignore[arg-type]

    assert bm.intercept(EncoderEvent(controller=_make_encoder(), rotations=1)) is False


# ---------------------------------------------------------------------------
# Handler-level integration
# ---------------------------------------------------------------------------


def test_blend_mode_intercept_blocks_switch_events_from_its_own_controller():
    """SwitchEvents from the blend input controller must not trigger interpolation."""
    enc = _make_encoder(id_=1)
    ic, setter = _make_ic(enc)
    bm = BlendMode(MagicMock(), {"name": "Test", "input_id": 1})  # type: ignore[arg-type]
    bm.input_controller = ic

    switch_event = SwitchEvent(controller=enc, kind=SwitchEventKind.PRESS)
    assert bm.intercept(switch_event) is False
    setter.send_parameter.assert_not_called()
