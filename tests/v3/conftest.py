"""
Shared fixtures and helpers for v3 (Pistomptre + Modhandler) integration tests.
"""
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

import common.token as Token

PROJECT_ROOT = Path(__file__).parent.parent.parent

with patch("pistomp.settings.Settings.load_settings"), patch("pistomp.settings.Settings.set_setting"):
    from modalapi.modhandler import Modhandler
    from pistomp.pistomptre import Pistomptre


# ---------------------------------------------------------------------------
# Factory fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def make_plugin():
    from modalapi.plugin import Plugin
    from modalapi.parameter import Parameter

    def _make(instance_id, category="Distortion", bypassed=False, has_footswitch=False, parameters=None):
        if parameters is None:
            parameters = {}
        bypass_info = {"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}
        bypass_param = Parameter(bypass_info, bypassed, None, instance_id)
        parameters[":bypass"] = bypass_param
        p = Plugin(instance_id, parameters, {}, category)
        p.has_footswitch = has_footswitch
        return p

    return _make


@pytest.fixture
def make_parameter():
    from modalapi.parameter import Parameter

    def _make(name, instance_id, value=0.5, minimum=0.0, maximum=1.0):
        info = {"shortName": name, "symbol": name.lower(), "ranges": {"minimum": minimum, "maximum": maximum}}
        return Parameter(info, value, None, instance_id)

    return _make


@pytest.fixture
def get_urls():
    """Return a helper that extracts called URLs from a mock."""
    def _get(mock_obj):
        return [call.args[0] for call in mock_obj.call_args_list]
    return _get


# ---------------------------------------------------------------------------
# Full-stack fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def v3_system(fake_lcd, tmp_path):
    cwd = str(PROJECT_ROOT)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    last_json = data_dir / "last.json"
    last_json.write_text(json.dumps({"pedalboard": "/path/to/rig.pedalboard"}))

    Modhandler._Modhandler__single = None  # pyright: ignore[reportAttributeAccessIssue]
    Pistomptre._Pistomptre__single = None  # pyright: ignore[reportAttributeAccessIssue]

    with (
        patch("requests.get") as mock_get,
        patch("requests.post") as mock_post,
        patch("pistomp.settings.Settings") as _mock_settings,
        patch("modalapi.pedalboard.Pedalboard.load_bundle"),
        patch("modalapi.wifi.WifiManager"),
        patch("subprocess.check_output", return_value=b"SystemState=running"),
        patch("pistomp.lcd320x240.LcdIli9341", return_value=fake_lcd),
    ):
        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "pedalboard/list" in url:
                resp.text = json.dumps([
                    {Token.TITLE: "Integration Rig", Token.BUNDLE: "/path/to/rig.pedalboard"},
                    {Token.TITLE: "New Rig",         Token.BUNDLE: "/path/to/new.pedalboard"},
                ])
            elif "snapshot/list" in url:
                resp.text = json.dumps({"0": "Clean", "1": "Lead"})
            elif "snapshot/name" in url:
                resp.text = json.dumps({"name": "Clean"})
            else:
                resp.text = "{}"
            return resp

        mock_get.side_effect = get_side_effect

        def post_side_effect(*args, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = "{}"
            return resp

        mock_post.side_effect = post_side_effect

        cfg_path = PROJECT_ROOT / "setup" / "config_templates" / "default_config_pistomptre.yml"
        with open(cfg_path, "r") as f:
            cfg = yaml.safe_load(f)

        mock_audiocard = MagicMock()
        handler = Modhandler(mock_audiocard, cwd, data_dir=str(data_dir))

        midiout = MagicMock()
        hw = Pistomptre(cfg, handler, midiout, handler.update_lcd_fs)
        handler.add_hardware(hw)

        handler.load_pedalboards()

        pb = handler.pedalboards["/path/to/rig.pedalboard"]
        pb.plugins = []
        handler.set_current_pedalboard(pb)

        pb2 = handler.pedalboards["/path/to/new.pedalboard"]
        pb2.plugins = []

        mock_get.reset_mock()
        mock_get.side_effect = get_side_effect
        mock_post.reset_mock()
        mock_post.side_effect = post_side_effect

        yield handler, hw, fake_lcd, mock_get, mock_post
