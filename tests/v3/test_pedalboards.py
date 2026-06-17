"""Pedalboard switching via MOD-UI file-watch and LCD encoder navigation — v3 LCD layout."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pistomp.switchstate as switchstate
from tests.types import SystemFixture


def test_v3_pedalboard_change_via_modui(v3_system: SystemFixture, make_plugin, snapshot):
    """MOD-UI writes last.json → poll_modui_changes() reloads without a load_bundle POST."""
    handler = v3_system.handler
    mock_get = v3_system.mock_get
    mock_post = v3_system.mock_post

    pb2 = handler.pedalboards["/path/to/new.pedalboard"]
    pb2.plugins = [make_plugin("fuzz", category="Distortion")]

    def get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = (
            json.dumps({"0": "Default"})
            if "snapshot/list" in url
            else json.dumps({"name": "Default"})
            if "snapshot/name" in url
            else "{}"
        )
        return resp

    mock_get.side_effect = get_side_effect

    last_json = Path(handler.data_dir) / "last.json"
    last_json.write_text(json.dumps({"pedalboard": "/path/to/new.pedalboard"}))
    os.utime(last_json, (9999, 9999))

    handler.poll_modui_changes()

    post_urls = [c.args[0] for c in mock_post.call_args_list]
    assert not any("load_bundle" in u for u in post_urls)
    assert handler.current
    assert handler.current.pedalboard.title == "New Rig"
    snapshot()


def test_v3_pedalboard_change_via_lcd(v3_system: SystemFixture, make_plugin, snapshot, get_urls):
    """Encoder selects the second board → POST load_bundle fires, MOD-UI confirms via last.json."""
    handler = v3_system.handler
    mock_get = v3_system.mock_get
    mock_post = v3_system.mock_post

    handler.pedalboards["/path/to/new.pedalboard"].plugins = [make_plugin("fuzz")]

    handler.universal_encoder_select(1)
    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    handler.universal_encoder_select(1)
    handler.universal_encoder_sw(switchstate.Value.RELEASED)

    assert any("pedalboard/load_bundle" in u for u in get_urls(mock_post))
    assert any("reset" in u for u in get_urls(mock_get))

    def get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = (
            json.dumps({"0": "Default"})
            if "snapshot/list" in url
            else json.dumps({"name": "Default"})
            if "snapshot/name" in url
            else "{}"
        )
        return resp

    mock_get.reset_mock()
    mock_get.side_effect = get_side_effect

    last_json = Path(handler.data_dir) / "last.json"
    last_json.write_text(json.dumps({"pedalboard": "/path/to/new.pedalboard"}))
    os.utime(last_json, (9999, 9999))
    handler.poll_modui_changes()

    assert handler.current
    assert handler.current.pedalboard.title == "New Rig"
    snapshot()



def test_v3_outbound_ws_suppressed_during_pedalboard_change(v3_system: SystemFixture, make_plugin):
    """While a pedalboard change is in flight, outbound param_set messages are dropped."""
    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge

    # Start with a loaded pedalboard
    old_plugin = make_plugin("old_fuzz", category="Distortion", bypassed=False)
    assert handler.current is not None
    handler.current.pedalboard.plugins = [old_plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, handler.hardware.footswitches)
    handler.lcd.draw_main_panel()
    widget = next(w for w in handler.lcd.w_plugins if w.object is old_plugin)
    ws_bridge.sent.clear()

    # Simulate a user tapping the bypass on the old pedalboard while a change is in flight
    handler._is_pedalboard_loading = True
    handler.toggle_plugin_bypass(widget, old_plugin)

    # The bypass should flip locally, but NO ws message should be sent
    assert old_plugin.is_bypassed()
    assert ws_bridge.sent_values_for("old_fuzz", ":bypass") == []

    # After clearing suppression, sends resume
    handler._is_pedalboard_loading = False
    handler.toggle_plugin_bypass(widget, old_plugin)
    assert not old_plugin.is_bypassed()
    assert ws_bridge.sent_values_for("old_fuzz", ":bypass") == [0.0]


def test_v3_loading_start_suppresses_outbound_ws(v3_system: SystemFixture):
    """Receiving loading_start from MOD-UI sets the suppression flag."""
    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge

    assert not getattr(handler, "_is_pedalboard_loading", False)
    ws_bridge.inject("loading_start 0")
    handler.poll_ws_messages()
    assert handler._is_pedalboard_loading is True


def test_v3_set_current_pedalboard_clears_suppression(v3_system: SystemFixture, make_plugin):
    """After set_current_pedalboard completes, suppression is cleared so normal operation resumes."""
    handler = v3_system.handler
    handler._is_pedalboard_loading = True
    assert handler.current is not None

    pb = handler.current.pedalboard
    new_plugin = make_plugin("new_fuzz", category="Distortion", bypassed=False)
    pb.plugins = [new_plugin]

    handler.set_current_pedalboard(pb)

    assert handler._is_pedalboard_loading is False
