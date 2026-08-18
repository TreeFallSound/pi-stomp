"""Modhandler._fire_blend_row / _rebuild_blend_layer — blend as a BLEND
context row (see "Pedalboard-level rows and blend as a context" in
pistomp/input/README.md), replacing the old upstream
active_blend_mode.intercept() short-circuit.

Verifies: when blend is attached to the same physical control as a
pedalboard MIDI binding, the pedalboard row is visibly SHADOWED (not
silently starved), and _fire_blend_row only fires for an actual BlendEffect
winner — a pedalboard-only control falls through to legacy dispatch untouched.
"""

from unittest.mock import MagicMock

from common.contexts import (
    BindingDecl,
    ContextKind,
    ContextLayer,
    ContextRef,
    ContextStack,
    ControlClass,
    ControlRef,
    EventKind,
    ParamEffect,
    ShadowState,
)
from common.parameter import Symbol
from blend.input_controller import InputController
from modalapi.modhandler import Modhandler
from pistomp.encoder_controller import EncoderController
from pistomp.input.event import EncoderEvent


def _encoder(midi_CC=70, midi_channel=0, id_=1):
    return EncoderController(d_pin=None, clk_pin=None, midi_CC=midi_CC, midi_channel=midi_channel, id=id_)


def _handler_with_pedalboard_row(control_id: str) -> tuple[Modhandler, ContextLayer]:
    h = object.__new__(Modhandler)
    h._blend_layer = ContextLayer(ref=ContextRef(kind=ContextKind.BLEND))
    pedalboard_layer = ContextLayer(ref=ContextRef(kind=ContextKind.PEDALBOARD))
    pedalboard_layer.add(
        BindingDecl(
            control=ControlRef(cls=ControlClass.ANALOG, id=control_id),
            event_kind=EventKind.ROTATE,
            effects=(ParamEffect(plugin=MagicMock(), symbol=Symbol("gain")),),
            context=pedalboard_layer.ref,
        )
    )
    h._controller_manager = MagicMock()
    h._controller_manager.effective_table = ContextStack(layers=[pedalboard_layer])
    return h, pedalboard_layer


def test_blend_attached_to_same_control_shadows_pedalboard_row_and_fires():
    enc = _encoder(midi_CC=70, midi_channel=0)
    h, pedalboard_layer = _handler_with_pedalboard_row("0:70")

    ic = MagicMock(spec=InputController)
    ic.controlled_input = enc
    ic.handle_event.return_value = True
    h.active_blend_mode = MagicMock(input_controller=ic)
    h._rebuild_blend_layer()

    consumed = h._fire_blend_row(EncoderEvent(controller=enc, rotations=1))

    assert consumed is True
    ic.handle_event.assert_called_once()
    row = pedalboard_layer.rows[(ControlClass.ANALOG, EventKind.ROTATE)][0]
    assert row.shadow_state is ShadowState.SHADOWED


def test_no_blend_attached_falls_through_to_legacy_dispatch():
    enc = _encoder(midi_CC=70, midi_channel=0)
    h, pedalboard_layer = _handler_with_pedalboard_row("0:70")
    h.active_blend_mode = None
    h._rebuild_blend_layer()

    consumed = h._fire_blend_row(EncoderEvent(controller=enc, rotations=1))

    assert consumed is False
    row = pedalboard_layer.rows[(ControlClass.ANALOG, EventKind.ROTATE)][0]
    assert row.shadow_state is ShadowState.ACTIVE


def test_blend_attached_to_a_different_control_leaves_this_row_untouched():
    enc = _encoder(midi_CC=70, midi_channel=0)
    other_enc = _encoder(midi_CC=71, midi_channel=0, id_=2)
    h, pedalboard_layer = _handler_with_pedalboard_row("0:70")

    ic = MagicMock(spec=InputController)
    ic.controlled_input = other_enc
    h.active_blend_mode = MagicMock(input_controller=ic)
    h._rebuild_blend_layer()

    consumed = h._fire_blend_row(EncoderEvent(controller=enc, rotations=1))

    assert consumed is False
    ic.handle_event.assert_not_called()
    row = pedalboard_layer.rows[(ControlClass.ANALOG, EventKind.ROTATE)][0]
    assert row.shadow_state is ShadowState.ACTIVE
