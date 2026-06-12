"""Startup, basic navigation, and footswitch press — smoke tests for the full stack."""

import pistomp.switchstate as switchstate
import common.token as Token
from pistomp.encoder_controller import EncoderController
from pistomp.input.event import SwitchEventKind


def test_v3_startup_snapshot(v3_system, snapshot):
    lcd = v3_system.lcd
    assert len(lcd.frames) > 0
    snapshot()


def test_v3_nav_to_system_menu(v3_system, snapshot):
    """Wrench is initially selected; clicking encoder opens the system menu."""
    handler = v3_system.handler
    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    snapshot()


def test_v3_footswitch_press(v3_system, snapshot):
    """Footswitch 0 toggles enabled, sends MIDI CC 60, and updates the LCD."""
    handler = v3_system.handler
    hw = v3_system.hw
    midiout = hw.midiout

    hw.footswitches[0]._on_switch(switchstate.Value.RELEASED)

    midiout.send_message.assert_called_once()
    cc_msg = midiout.send_message.call_args[0][0]
    assert cc_msg[1] == 60   # midi_CC from default config
    assert cc_msg[2] == 127  # enabled → 127

    snapshot()


def test_v3_nav_encoder_button_press_opens_system_menu(v3_system, snapshot):
    """Nav encoder button press routes through the sink pipeline to lcd.enc_sw."""
    hw = v3_system.hw

    nav_enc = next(e for e in hw.encoders if isinstance(e, EncoderController) and e.type == Token.NAV)
    nav_enc._on_button(switchstate.Value.RELEASED, timestamp=0.0)

    snapshot()


def test_v3_tweak_encoder_longpress_fires_callback(v3_system, get_urls):
    """Tweak encoder longpress resolves its named callback through the sink pipeline.

    enc1's default longpress is 'previous_snapshot'; at index 0 it wraps to the max.
    """
    handler = v3_system.handler
    hw = v3_system.hw
    mock_get = v3_system.mock_get

    enc1 = next(e for e in hw.encoders if isinstance(e, EncoderController) and getattr(e, "id", None) == 1)
    assert enc1.longpress == "previous_snapshot"

    enc1._on_button_longpress(switchstate.Value.LONGPRESSED, timestamp=0.0)

    assert any("snapshot/load" in u for u in get_urls(mock_get))
