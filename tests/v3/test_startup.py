"""Startup, basic navigation, and footswitch press — smoke tests for the full stack."""

import pistomp.switchstate as switchstate


def test_v3_startup_snapshot(v3_system, snapshot):
    _, _, lcd, _, _ = v3_system
    assert len(lcd.frames) > 0
    snapshot()


def test_v3_nav_to_system_menu(v3_system, snapshot):
    """Wrench is initially selected; clicking encoder opens the system menu."""
    handler, _, _, _, _ = v3_system
    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    snapshot()


def test_v3_footswitch_press(v3_system, snapshot):
    """Footswitch 0 toggles enabled, sends MIDI CC 60, and updates the LCD."""
    handler, hw, _, _, _ = v3_system
    midiout = hw.midiout

    hw.footswitches[0].pressed(switchstate.Value.RELEASED)

    midiout.send_message.assert_called_once()
    cc_msg = midiout.send_message.call_args[0][0]
    assert cc_msg[1] == 60   # midi_CC from default config
    assert cc_msg[2] == 127  # enabled → 127

    snapshot()
