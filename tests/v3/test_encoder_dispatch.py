"""Characterization tests for the v3 encoder dispatch fall-through.

These pin the CURRENT behavior of ``Modhandler._handle_encoder`` for the
main-panel case (no fullscreen panel mounted). The top-of-stack input-routing
refactor must preserve this bit-for-bit:

  * tweak encoders (id 1/2, type KNOB, CC 70/71) → ``_emit_midi`` absolute CC
    on ``hardware.midiout``.
  * volume encoder (id 3, type VOLUME) → ``audiocard.set_volume_parameter(MASTER)``.
  * with no fullscreen panel mounted, ``lcd.handle`` returns False so the event
    falls through to the handler cascade.

Driven through the *real* encoders (correct id/type/CC from config) via the
public ``handler.handle`` sink entry point. The complementary fullscreen-panel
seam (``lcd.handle`` consuming ids 1-3) is pinned by ``test_graphic_eq_panel``.
"""

from typing import cast
from unittest.mock import MagicMock

import common.token as Token
from common.contexts import (
    BindingDecl,
    ContextKind,
    ContextLayer,
    ContextRef,
    ContextStack,
    ControlClass,
    ControlRef,
    EventKind,
    MidiCcEffect,
)
from pistomp.encoder_controller import EncoderController
from pistomp.input.event import EncoderEvent
from rtmidi.midiconstants import CONTROL_CHANGE
from tests.types import SystemFixture
from uilib.misc import InputEvent


def _enc(hw, enc_id: int) -> EncoderController:
    enc = next((e for e in hw.encoders if getattr(e, "id", None) == enc_id), None)
    assert enc is not None, f"no encoder with id={enc_id}"
    return enc


def _prime_main_panel(v3_system: SystemFixture) -> None:
    """Draw the main panel with no fullscreen panel mounted."""
    handler = v3_system.handler
    hw = v3_system.hw
    assert handler.current
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    assert handler.lcd.pstack.current is handler.lcd.main_panel


# ---------------------------------------------------------------------------
# Encoder id/type mapping sanity — the premise of the routing refactor
# ---------------------------------------------------------------------------


def test_v3_encoder_id_type_mapping(v3_system: SystemFixture):
    """Default v3 config: nav=NAV/id None, 1&2=KNOB CC70/71, 3=VOLUME."""
    hw = v3_system.hw
    by_id = {getattr(e, "id", None): e for e in hw.encoders}

    assert by_id[1].type == Token.KNOB
    assert by_id[1].midi_CC == 70
    assert by_id[2].type == Token.KNOB
    assert by_id[2].midi_CC == 71
    assert by_id[3].type == Token.VOLUME

    nav = next(e for e in hw.encoders if e.type == Token.NAV)
    assert nav.id is None


# ---------------------------------------------------------------------------
# Gap 1 — main-panel tweak encoders emit an absolute MIDI CC
# ---------------------------------------------------------------------------


def test_main_panel_tweak1_emits_cc70(v3_system: SystemFixture):
    _prime_main_panel(v3_system)
    hw = v3_system.hw

    enc1 = _enc(hw, 1)
    # Unbound tweak seeds its fallback CC at 64; one detent advances it to 65.
    enc1.refresh(1)

    hw.midiout.send_message.assert_called_with([enc1.midi_channel | CONTROL_CHANGE, 70, 65])


def test_main_panel_tweak2_emits_cc71(v3_system: SystemFixture):
    _prime_main_panel(v3_system)
    hw = v3_system.hw

    enc2 = _enc(hw, 2)
    # Seed 64; one CCW detent advances the fallback CC to 63.
    enc2.refresh(-1)

    hw.midiout.send_message.assert_called_with([enc2.midi_channel | CONTROL_CHANGE, 71, 63])


# ---------------------------------------------------------------------------
# Gap 2 — main-panel volume encoder drives the audio card, not MIDI
# ---------------------------------------------------------------------------


def test_main_panel_volume_encoder_sets_audiocard_master(v3_system: SystemFixture):
    _prime_main_panel(v3_system)
    handler = v3_system.handler
    hw = v3_system.hw

    # VOLUME branch requires the encoder to be bound to a parameter.
    handler.bind_volume_encoder()
    enc3 = _enc(hw, 3)
    assert enc3.parameter is not None

    from common.parameter_steps import ParameterSteps

    expected = ParameterSteps.for_parameter(enc3.parameter).move(1)
    enc3.refresh(1)

    cast(MagicMock, handler.audiocard.set_volume_parameter).assert_called_with(handler.audiocard.MASTER, expected)
    assert enc3.parameter.value == expected
    # Volume goes to the audio card, never to MIDI.
    hw.midiout.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# Gap 1 (seam) — with no fullscreen panel, lcd.handle does not consume
# ---------------------------------------------------------------------------


def test_lcd_handle_falls_through_without_fullscreen_panel(v3_system: SystemFixture):
    _prime_main_panel(v3_system)
    handler = v3_system.handler
    hw = v3_system.hw

    for enc_id in (1, 2, 3):
        event = EncoderEvent(controller=_enc(hw, enc_id), rotations=1)
        assert handler.lcd.handle(event) is False, f"enc {enc_id} should fall through on main panel"


# ---------------------------------------------------------------------------
# Gap 3 — the ParameterDialog's NAV-driven value change must still emit CC
# ---------------------------------------------------------------------------


def test_parameter_dialog_nav_change_emits_cc_for_external_param(v3_system: SystemFixture):
    """Turning the physical tweak encoder emits a CC via Modhandler._handle_encoder
    (see test_main_panel_tweak1_emits_cc70). But opening that same external-CC
    parameter's dialog and changing its value with NAV goes through
    Parameterdialog.parameter_value_change -> Lcd.parameter_commit ->
    Modhandler.parameter_value_commit, which historically short-circuited on
    EXTERNAL_INSTANCE_ID as "local-only" and never sent the CC."""
    _prime_main_panel(v3_system)
    handler = v3_system.handler
    hw = v3_system.hw

    enc1 = _enc(hw, 1)
    ext_param = hw.create_external_parameter("virtual", enc1.midi_channel, enc1.midi_CC)
    enc1.bind_to_parameter(ext_param)
    binding = f"{enc1.midi_channel}:{enc1.midi_CC}"
    hw.controllers[binding] = enc1
    handler._controller_manager.effective_table = ContextStack(
        layers=[
            ContextLayer(
                ref=ContextRef(kind=ContextKind.PEDALBOARD),
                rows={
                    (ControlClass.ANALOG, EventKind.ROTATE): [
                        BindingDecl(
                            control=ControlRef(cls=ControlClass.ANALOG, id=binding),
                            event_kind=EventKind.ROTATE,
                            effects=(MidiCcEffect(cc_ref=binding),),
                            context=ContextRef(kind=ContextKind.PEDALBOARD),
                        )
                    ]
                },
            )
        ]
    )

    d = handler.lcd.draw_parameter_dialog(ext_param)
    hw.midiout.send_message.reset_mock()

    d.input_event(InputEvent.RIGHT)

    hw.midiout.send_message.assert_called_once()
    sent_cc = hw.midiout.send_message.call_args[0][0]
    assert sent_cc[0] == (enc1.midi_channel | CONTROL_CHANGE)
    assert sent_cc[1] == enc1.midi_CC


# ---------------------------------------------------------------------------
# Bug #2 — a tweak turn while a Parameterdialog is open must not leak to the
# pedalboard-bound parameter underneath. The dialog declares a PANEL row for
# its badged tweak so the binding table resolves it there (same shape as
# PluginPanel/ParameterWindow) instead of falling through to
# Modhandler._handle_encoder's unconditional c.parameter.value write + CC.
# ---------------------------------------------------------------------------


def _open_dialog_for_param(v3_system, param, *, tweak_id: int | None = None):
    """Push a Parameterdialog for *param* and (optionally) badge it with a
    tweak id, mirroring what draw_parameter_dialog does for an external CC."""
    handler = v3_system.handler
    d = handler.lcd.draw_parameter_dialog(param)
    if tweak_id is not None:
        from uilib.glyphs.badge import BadgeGlyph
        d.set_tweak_badge(tweak_id, BadgeGlyph(str(tweak_id)))
    return d


def test_tweak_bound_to_different_param_does_not_corrupt_it(v3_system: SystemFixture):
    """Tweak1 is bound to param B. A dialog is open for param A. Turning
    tweak1 edits A (the dialog) and must NOT write B or emit B's CC."""
    _prime_main_panel(v3_system)
    handler = v3_system.handler
    hw = v3_system.hw

    enc1 = _enc(hw, 1)
    # Param B: the pedalboard-bound param tweak1 normally drives.
    bound_param = hw.create_external_parameter("virtual", enc1.midi_channel, enc1.midi_CC)
    enc1.bind_to_parameter(bound_param)
    binding = f"{enc1.midi_channel}:{enc1.midi_CC}"
    hw.controllers[binding] = enc1
    handler._controller_manager.effective_table = ContextStack(
        layers=[
            ContextLayer(
                ref=ContextRef(kind=ContextKind.PEDALBOARD),
                rows={
                    (ControlClass.ANALOG, EventKind.ROTATE): [
                        BindingDecl(
                            control=ControlRef(cls=ControlClass.ANALOG, id=binding),
                            event_kind=EventKind.ROTATE,
                            effects=(MidiCcEffect(cc_ref=binding),),
                            context=ContextRef(kind=ContextKind.PEDALBOARD),
                        )
                    ]
                },
            )
        ]
    )

    # Param A: a different plugin param, opened as a dialog badged to tweak1.
    from tests.conftest import PortInfo
    from common.parameter import Parameter

    info: PortInfo = {"shortName": "tone", "symbol": "tone", "ranges": {"minimum": 0.0, "maximum": 1.0}}
    dialog_param = Parameter(info, 0.5, None, "other_plugin")
    handler.lcd.w_parameter_dialogs[dialog_param.name] = None  # avoid dedup
    d = _open_dialog_for_param(v3_system, dialog_param, tweak_id=1)
    from uilib.parameterdialog import Parameterdialog as _PD
    assert isinstance(d, _PD) and d._tweak_id == 1

    bound_before = bound_param.value
    dialog_before = dialog_param.value
    hw.midiout.send_message.reset_mock()

    # Drive the REAL path: refresh() is where the old shadow-accumulator leak
    # lived (it wrote c.parameter.value before dispatch). A hand-built event
    # can't catch that; enc1.refresh(1) can.
    enc1.refresh(1)

    # The dialog's parameter changed (the dialog consumed the tweak).
    assert dialog_param.value != dialog_before
    # The bound parameter underneath was NOT corrupted.
    assert bound_param.value == bound_before
    # No CC emitted — the dialog consumed the event before _handle_encoder.
    hw.midiout.send_message.assert_not_called()


def test_unbound_tweak_with_dialog_open_still_emits_cc(v3_system: SystemFixture):
    """An unbound tweak turn while a dialog is open (dialog badged to a
    different tweak, or the turning tweak has no row) still emits its CC —
    the MIDI-learn axiom (input/README.md). The dialog does not update."""
    _prime_main_panel(v3_system)
    handler = v3_system.handler
    hw = v3_system.hw

    enc2 = _enc(hw, 2)  # tweak2, unbound
    from tests.conftest import PortInfo
    from common.parameter import Parameter

    info: PortInfo = {"shortName": "tone", "symbol": "tone", "ranges": {"minimum": 0.0, "maximum": 1.0}}
    dialog_param = Parameter(info, 0.5, None, "some_plugin")
    handler.lcd.w_parameter_dialogs[dialog_param.name] = None
    # Dialog badged to tweak1, not tweak2 — tweak2 has no row on the dialog.
    _open_dialog_for_param(v3_system, dialog_param, tweak_id=1)

    dialog_before = dialog_param.value
    hw.midiout.send_message.reset_mock()

    enc2.refresh(1)

    # Dialog unchanged — tweak2 has no row on it.
    assert dialog_param.value == dialog_before
    # CC still emitted (MIDI-learn axiom — unbound tweak must reach mod-ui).
    hw.midiout.send_message.assert_called_once()
    sent_cc = hw.midiout.send_message.call_args[0][0]
    assert sent_cc[1] == 71  # enc2's CC


def test_tweak_bound_to_same_param_as_dialog_edits_once(v3_system: SystemFixture):
    """Tweak1 bound to the same param the dialog shows. The dialog consumes
    the tweak (single update), and no double-apply via _handle_encoder."""
    _prime_main_panel(v3_system)
    handler = v3_system.handler
    hw = v3_system.hw

    enc1 = _enc(hw, 1)
    ext_param = hw.create_external_parameter("virtual", enc1.midi_channel, enc1.midi_CC)
    enc1.bind_to_parameter(ext_param)
    binding = f"{enc1.midi_channel}:{enc1.midi_CC}"
    hw.controllers[binding] = enc1
    handler._controller_manager.effective_table = ContextStack(
        layers=[
            ContextLayer(
                ref=ContextRef(kind=ContextKind.PEDALBOARD),
                rows={
                    (ControlClass.ANALOG, EventKind.ROTATE): [
                        BindingDecl(
                            control=ControlRef(cls=ControlClass.ANALOG, id=binding),
                            event_kind=EventKind.ROTATE,
                            effects=(MidiCcEffect(cc_ref=binding),),
                            context=ContextRef(kind=ContextKind.PEDALBOARD),
                        )
                    ]
                },
            )
        ]
    )

    handler.lcd.draw_parameter_dialog(ext_param)
    # draw_parameter_dialog already badges it to tweak1 via tweak_badge_number.
    hw.midiout.send_message.reset_mock()
    before = ext_param.value

    enc1.refresh(1)

    # The parameter changed exactly once (no double-apply from _handle_encoder).
    assert ext_param.value != before
    # The CC is emitted exactly once — via the dialog's parameter_value_commit
    # path (which owns the CC for external params), NOT via _handle_encoder.
    # One call, not two: the dialog consumed the event before the leak.
    assert hw.midiout.send_message.call_count == 1
    sent_cc = hw.midiout.send_message.call_args[0][0]
    assert sent_cc[0] == (enc1.midi_channel | CONTROL_CHANGE)
    assert sent_cc[1] == enc1.midi_CC
