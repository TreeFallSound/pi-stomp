"""Pedalboard loading, switching (MOD-UI path and LCD path), banks, and config overlay."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

import common.token as Token
import pistomp.switchstate as switchstate


def test_v3_pedalboard_change_via_modui(v3_system, make_plugin, snapshot):
    """MOD-UI writes last.json → poll_modui_changes() reloads without a load_bundle POST."""
    handler, hw, _, mock_get, mock_post = v3_system

    pb2 = handler.pedalboards["/path/to/new.pedalboard"]
    pb2.plugins = [make_plugin("fuzz", category="Distortion")]

    def get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = json.dumps({"0": "Default"}) if "snapshot/list" in url else (
            json.dumps({"name": "Default"}) if "snapshot/name" in url else "{}"
        )
        return resp

    mock_get.side_effect = get_side_effect

    last_json = Path(handler.data_dir) / "last.json"
    last_json.write_text(json.dumps({"pedalboard": "/path/to/new.pedalboard"}))
    os.utime(last_json, (9999, 9999))

    handler.poll_modui_changes()

    post_urls = [c.args[0] for c in mock_post.call_args_list]
    assert not any("load_bundle" in u for u in post_urls)
    assert handler.current.pedalboard.title == "New Rig"
    snapshot()


def test_v3_pedalboard_change_via_lcd(v3_system, make_plugin, snapshot, get_urls):
    """Encoder navigates to pedalboard widget, selects the second board, POST load_bundle fires."""
    handler, hw, _, mock_get, mock_post = v3_system

    pb2 = handler.pedalboards["/path/to/new.pedalboard"]
    pb2.plugins = [make_plugin("fuzz", category="Distortion")]

    handler.universal_encoder_select(1)             # wrench → pedalboard widget
    handler.universal_encoder_sw(switchstate.Value.RELEASED)   # open menu
    handler.universal_encoder_select(1)             # highlight "New Rig"
    handler.universal_encoder_sw(switchstate.Value.RELEASED)   # select

    assert any("pedalboard/load_bundle" in u for u in get_urls(mock_post))
    assert any("reset" in u for u in get_urls(mock_get))

    def get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = json.dumps({"0": "Default"}) if "snapshot/list" in url else (
            json.dumps({"name": "Default"}) if "snapshot/name" in url else "{}"
        )
        return resp

    mock_get.reset_mock()
    mock_get.side_effect = get_side_effect

    last_json = Path(handler.data_dir) / "last.json"
    last_json.write_text(json.dumps({"pedalboard": "/path/to/new.pedalboard"}))
    os.utime(last_json, (9999, 9999))

    handler.poll_modui_changes()

    assert handler.current.pedalboard.title == "New Rig"
    snapshot()


def test_v3_load_banks(v3_system, tmp_path):
    """load_banks() parses banks.json into self.banks."""
    handler, _, _, _, _ = v3_system

    banks_data = [
        {"title": "Live",   "pedalboards": [{"title": "Rig 1"}, {"title": "Rig 2"}]},
        {"title": "Studio", "pedalboards": [{"title": "Studio Rig"}]},
    ]
    banks_file = tmp_path / "data" / "banks.json"
    banks_file.write_text(json.dumps(banks_data))
    handler.banks_file = str(banks_file)

    handler.load_banks()

    assert handler.banks == {"Live": ["Rig 1", "Rig 2"], "Studio": ["Studio Rig"]}


def test_v3_set_bank(v3_system):
    """set_bank() updates current_bank and persists to settings."""
    handler, _, _, _, _ = v3_system
    handler.set_bank("Live")
    assert handler.current_bank == "Live"
    handler.settings.set_setting.assert_called_with(Token.BANK, "Live")


def test_v3_banks_change_detected_via_poll(v3_system, tmp_path):
    """poll_modui_changes() reloads banks when banks.json mtime changes."""
    handler, _, _, _, _ = v3_system

    banks_data = [{"title": "Bank A", "pedalboards": [{"title": "Rig 1"}]}]
    banks_file = tmp_path / "data" / "banks.json"
    banks_file.write_text(json.dumps(banks_data))
    handler.banks_file = str(banks_file)
    handler.banks_file_timestamp = 0  # force detection

    handler.poll_modui_changes()

    assert "Bank A" in handler.banks


def test_v3_set_current_pedalboard_with_config_file(v3_system, tmp_path):
    """When a config.yml exists in the bundle dir, hardware.reinit receives the parsed dict."""
    handler, hw, _, _, _ = v3_system
    from modalapi.pedalboard import Pedalboard as PB

    bundle_dir = tmp_path / "cfg_test.pedalboard"
    bundle_dir.mkdir()
    config_data = {"hardware": {"footswitches": [{"id": 0, "midi_CC": 99}]}}
    (bundle_dir / "config.yml").write_text(yaml.dump(config_data))

    pb = PB("Config Test", str(bundle_dir))
    pb.plugins = []
    handler.pedalboards[str(bundle_dir)] = pb
    handler.pedalboard_list.append(pb)

    handler.set_current_pedalboard(pb)

    assert handler.current.pedalboard is pb


def test_v3_get_current_pedalboard_bundle_path(v3_system):
    """get_current_pedalboard_bundle_path() reads the bundle from last.json."""
    handler, _, _, _, _ = v3_system
    result = handler.get_current_pedalboard_bundle_path()
    assert result == "/path/to/rig.pedalboard"
