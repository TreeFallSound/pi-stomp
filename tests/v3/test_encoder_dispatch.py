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
from modalapi.external_midi import EXTERNAL_INSTANCE_ID
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
    handler = v3_system.handler
    hw = v3_system.hw

    enc1 = _enc(hw, 1)
    event = EncoderEvent(controller=enc1, rotations=1, new_value=0.0, new_midi_value=64)
    assert handler.handle(event) is True

    hw.midiout.send_message.assert_called_with([enc1.midi_channel | CONTROL_CHANGE, 70, 64])


def test_main_panel_tweak2_emits_cc71(v3_system: SystemFixture):
    _prime_main_panel(v3_system)
    handler = v3_system.handler
    hw = v3_system.hw

    enc2 = _enc(hw, 2)
    event = EncoderEvent(controller=enc2, rotations=-1, new_value=0.0, new_midi_value=13)
    assert handler.handle(event) is True

    hw.midiout.send_message.assert_called_with([enc2.midi_channel | CONTROL_CHANGE, 71, 13])


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

    event = EncoderEvent(controller=enc3, rotations=1, new_value=-5.0, new_midi_value=0)
    assert handler.handle(event) is True

    cast(MagicMock, handler.audiocard.set_volume_parameter).assert_called_with(handler.audiocard.MASTER, -5.0)
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
        event = EncoderEvent(controller=_enc(hw, enc_id), rotations=1, new_value=0.0, new_midi_value=0)
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
    ext_param = hw.create_external_parameter(enc1, "virtual", enc1.midi_channel, enc1.midi_CC)
    enc1.bind_to_parameter(ext_param)
    hw.controllers["0:70"] = enc1

    d = handler.lcd.draw_parameter_dialog(ext_param)
    hw.midiout.send_message.reset_mock()

    d.input_event(InputEvent.RIGHT)

    hw.midiout.send_message.assert_called_once()
    sent_cc = hw.midiout.send_message.call_args[0][0]
    assert sent_cc[0] == (enc1.midi_channel | CONTROL_CHANGE)
    assert sent_cc[1] == enc1.midi_CC
