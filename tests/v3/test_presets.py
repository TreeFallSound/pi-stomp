"""Preset navigation requiring v3 hardware interactions (longpress, LCD encoder menu)."""

import time
from unittest.mock import patch

import pistomp.switchstate as switchstate
from pistomp.footswitch import Footswitch
from tests.types import SystemFixture


def test_v3_preset_change_via_footswitch_longpress(v3_system: SystemFixture, snapshot, get_urls):
    """Footswitch 0 longpress fires previous_snapshot → wraps from 0 to max index."""
    handler, hw, _, mock_get, _ = v3_system

    hw.footswitches[0].pressed(switchstate.Value.LONGPRESSED)
    with patch("time.monotonic", return_value=time.monotonic() + 1.0):
        Footswitch.check_longpress_events()

    assert any("snapshot/load" in u for u in get_urls(mock_get))
    snapshot()


def test_v3_preset_change_via_lcd(v3_system: SystemFixture, snapshot, get_urls):
    """Encoder navigates to preset widget, opens menu, selects 'Lead', fires snapshot/load."""
    handler, _, _, mock_get, _ = v3_system

    snapshot("nav_A")

    handler.universal_encoder_select(1)
    handler.universal_encoder_select(1)
    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    snapshot("nav_B")

    handler.universal_encoder_select(1)
    snapshot("nav_C")

    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    assert any("snapshot/load?id=1" in u for u in get_urls(mock_get))
    snapshot("nav_D")
