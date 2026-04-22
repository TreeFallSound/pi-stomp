"""Pedalboard switching via MOD-UI file-watch and LCD encoder navigation — v3 LCD layout."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pistomp.switchstate as switchstate
from tests.types import SystemFixture


def test_v3_pedalboard_change_via_modui(v3_system: SystemFixture, make_plugin, snapshot):
    """MOD-UI writes last.json → poll_modui_changes() reloads without a load_bundle POST."""
    handler, _, _, mock_get, mock_post = v3_system

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
    handler, _, _, mock_get, mock_post = v3_system

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
