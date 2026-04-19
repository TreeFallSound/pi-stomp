"""Preset (snapshot) navigation: longpress, LCD menu, incr/decr, direct set, out-of-range."""

import time
from unittest.mock import patch, MagicMock
import json

import pistomp.switchstate as switchstate
from pistomp.footswitch import Footswitch


def test_v3_preset_change_via_footswitch_longpress(v3_system, snapshot, get_urls):
    """Footswitch 0 longpress fires previous_snapshot → wraps from 0 to max index."""
    handler, hw, _, mock_get, _ = v3_system

    hw.footswitches[0].pressed(switchstate.Value.LONGPRESSED)

    with patch("time.monotonic", return_value=time.monotonic() + 1.0):
        Footswitch.check_longpress_events()

    assert any("snapshot/load" in u for u in get_urls(mock_get))
    snapshot()


def test_v3_preset_change_via_lcd(v3_system, snapshot, get_urls):
    """Encoder navigates to preset widget, opens menu, selects 'Lead', fires snapshot/load."""
    handler, _, _, mock_get, _ = v3_system

    snapshot("nav_A")   # main panel, wrench selected

    handler.universal_encoder_select(1)  # pedalboard widget
    handler.universal_encoder_select(1)  # preset widget
    handler.universal_encoder_sw(switchstate.Value.RELEASED)   # open menu
    snapshot("nav_B")   # menu open, "Clean" highlighted

    handler.universal_encoder_select(1)  # highlight "Lead"
    snapshot("nav_C")

    handler.universal_encoder_sw(switchstate.Value.RELEASED)   # select "Lead"

    assert any("snapshot/load?id=1" in u for u in get_urls(mock_get))
    snapshot("nav_D")   # back to main, "Lead" shown


def test_v3_preset_incr_and_change(v3_system, get_urls):
    """preset_incr_and_change() advances from index 0 → 1."""
    handler, _, _, mock_get, _ = v3_system

    handler.preset_incr_and_change()

    assert any("snapshot/load?id=1" in u for u in get_urls(mock_get))
    assert handler.current.preset_index == 1


def test_v3_preset_set_and_change(v3_system, get_urls):
    """preset_set_and_change(1) loads snapshot index 1 directly."""
    handler, _, _, mock_get, _ = v3_system

    handler.preset_set_and_change(1)

    assert any("snapshot/load?id=1" in u for u in get_urls(mock_get))


def test_v3_preset_change_out_of_range(v3_system, get_urls):
    """preset_change() with an invalid index shows a dialog and makes no HTTP call."""
    handler, _, _, mock_get, _ = v3_system

    handler.preset_change(99)

    assert not any("snapshot/load" in u for u in get_urls(mock_get))
