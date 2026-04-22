"""Pedalboard data and bank management."""

import json

import yaml

import common.token as Token
from tests.types import SystemFixture


def test_load_banks(modhandler_system: SystemFixture, tmp_path):
    handler, _, _, _, _ = modhandler_system
    banks_data = [
        {"title": "Live", "pedalboards": [{"title": "Rig 1"}, {"title": "Rig 2"}]},
        {"title": "Studio", "pedalboards": [{"title": "Studio Rig"}]},
    ]
    banks_file = tmp_path / "data" / "banks.json"
    banks_file.write_text(json.dumps(banks_data))
    handler.banks_file = str(banks_file)

    handler.load_banks()

    assert handler.banks == {"Live": ["Rig 1", "Rig 2"], "Studio": ["Studio Rig"]}


def test_set_bank(modhandler_system: SystemFixture):
    handler, _, _, _, _ = modhandler_system
    handler.set_bank("Live")
    assert handler.current_bank == "Live"
    handler.settings.set_setting.assert_called_with(Token.BANK, "Live")  # pyright: ignore[reportAttributeAccessIssue]


def test_banks_change_detected_via_poll(modhandler_system: SystemFixture, tmp_path):
    """poll_modui_changes() reloads banks when the file mtime changes."""
    handler, _, _, _, _ = modhandler_system
    banks_data = [{"title": "Bank A", "pedalboards": [{"title": "Rig 1"}]}]
    banks_file = tmp_path / "data" / "banks.json"
    banks_file.write_text(json.dumps(banks_data))
    handler.banks_file = str(banks_file)
    handler.banks_file_timestamp = 0

    handler.poll_modui_changes()

    assert "Bank A" in handler.banks


def test_set_current_pedalboard_with_config_file(modhandler_system: SystemFixture, tmp_path):
    """config.yml found in bundle dir is passed to hardware.reinit()."""
    handler, _, _, _, _ = modhandler_system
    from modalapi.pedalboard import Pedalboard as PB

    bundle_dir = tmp_path / "cfg_test.pedalboard"
    bundle_dir.mkdir()
    (bundle_dir / "config.yml").write_text(yaml.dump({"hardware": {}}))

    pb = PB("Config Test", str(bundle_dir))
    pb.plugins = []
    handler.pedalboards[str(bundle_dir)] = pb
    handler.pedalboard_list.append(pb)

    handler.set_current_pedalboard(pb)
    assert handler.current
    assert handler.current.pedalboard is pb


def test_get_current_pedalboard_bundle_path(modhandler_system: SystemFixture):
    handler, _, _, _, _ = modhandler_system
    assert handler.get_current_pedalboard_bundle_path() == "/path/to/rig.pedalboard"
