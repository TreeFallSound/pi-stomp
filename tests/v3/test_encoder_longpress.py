"""Encoder longpress dispatch through the binding table (Stage 4).

The configured longpress callback name (e.g. "next_snapshot") lives on the
encoder as a string and is resolved by the handler via ``get_callback``.
Stage 4 made the binding table the dispatch authority: ``ControllerManager``
builds a ``CallbackEffect`` LONGPRESS row keyed by the encoder's "channel:CC"
identity, and ``Modhandler._handle_switch`` resolves it instead of reading
``controller.longpress`` directly.
"""

from unittest.mock import MagicMock

from common.contexts import (
    BindingDecl,
    CallbackEffect,
    ContextKind,
    ContextRef,
    ControlClass,
    ControlRef,
    EventKind,
)
from pistomp.encoder_controller import EncoderController
from pistomp.input.event import SwitchEvent, SwitchEventKind
from tests.types import SystemFixture


def test_encoder_longpress_row_built_in_pedalboard_layer(v3_system: SystemFixture):
    """Encoders with a configured longpress produce a CallbackEffect LONGPRESS
    row in the PEDALBOARD layer, keyed by their "channel:CC" identity."""
    handler = v3_system.handler
    handler.bind_current_pedalboard()

    table = handler._controller_manager.effective_table
    # default_config_pistomptre.yml: encoder id 1 (CC70, longpress=previous_snapshot)
    # and id 2 (CC71, longpress=next_snapshot). Volume encoder id 3 has no longpress.
    enc1 = next(e for e in v3_system.hw.encoders if getattr(e, "id", None) == 1)
    enc2 = next(e for e in v3_system.hw.encoders if getattr(e, "id", None) == 2)
    key1 = f"{enc1.midi_channel}:{enc1.midi_CC}"
    key2 = f"{enc2.midi_channel}:{enc2.midi_CC}"

    rows = table.layers[0].rows.get((ControlClass.ANALOG, EventKind.LONGPRESS), [])
    by_id = {r.control.id: r for r in rows}

    assert key1 in by_id
    assert key2 in by_id
    assert all(isinstance(e, CallbackEffect) for r in by_id.values() for e in r.effects)
    effects_1 = [e for e in by_id[key1].effects if isinstance(e, CallbackEffect)]
    effects_2 = [e for e in by_id[key2].effects if isinstance(e, CallbackEffect)]
    assert effects_1[0].name == "previous_snapshot"
    assert effects_2[0].name == "next_snapshot"


def test_encoder_longpress_fires_callback_via_table(v3_system: SystemFixture):
    """A longpress SwitchEvent on a configured encoder resolves the table row
    and fires the named callback, rather than reading controller.longpress."""
    handler = v3_system.handler
    handler.bind_current_pedalboard()

    enc1 = next(e for e in v3_system.hw.encoders if getattr(e, "id", None) == 1)
    assert isinstance(enc1, EncoderController)
    assert enc1.midi_CC == 70

    fired: list[str] = []
    handler.callbacks["previous_snapshot"] = lambda: fired.append("prev")

    event = SwitchEvent(controller=enc1, kind=SwitchEventKind.LONGPRESS, timestamp=1000.0)
    assert handler.handle(event) is True

    assert fired == ["prev"]


def test_encoder_longpress_no_row_does_nothing(v3_system: SystemFixture):
    """An encoder with no longpress config (e.g. VOLUME) has no LONGPRESS row;
    the resolve returns None and nothing fires."""
    handler = v3_system.handler
    handler.bind_current_pedalboard()

    vol = next(e for e in v3_system.hw.encoders if getattr(e, "type", None) == "VOLUME")
    assert vol.midi_CC is None  # volume encoder has no midi_CC, no table row

    fired: list[str] = []
    original = handler.callbacks.copy()
    handler.callbacks["next_snapshot"] = lambda: fired.append("next")

    event = SwitchEvent(controller=vol, kind=SwitchEventKind.LONGPRESS, timestamp=1000.0)
    assert handler.handle(event) is True
    assert fired == []

    handler.callbacks = original


def test_encoder_longpress_explicit_row_fires(v3_system: SystemFixture):
    """Directly install a CallbackEffect row and confirm _fire_row dispatches
    it — isolates the fire path from the row-builder."""
    handler = v3_system.handler
    layer = handler._controller_manager.effective_table.layers[0]
    layer.rows.setdefault((ControlClass.ANALOG, EventKind.LONGPRESS), []).append(
        BindingDecl(
            control=ControlRef(cls=ControlClass.ANALOG, id="0:99"),
            event_kind=EventKind.LONGPRESS,
            effects=(CallbackEffect(name="toggle_bypass"),),
            context=ContextRef(kind=ContextKind.PEDALBOARD),
        )
    )

    fired: list[bool] = []
    handler.callbacks["toggle_bypass"] = lambda: fired.append(True)

    class _FakeEnc(EncoderController):
        pass

    enc = MagicMock(spec=EncoderController)
    enc.midi_channel = 0
    enc.midi_CC = 99
    event = SwitchEvent(controller=enc, kind=SwitchEventKind.LONGPRESS, timestamp=0.0)
    handler._handle_switch(event)
    assert fired == [True]