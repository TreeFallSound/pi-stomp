"""Startup must propagate WebSocket bridge failures — pi-stomp depends on it."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import common.token as Token

with patch("pistomp.settings.Settings.load_settings"), patch("pistomp.settings.Settings.set_setting"):
    from modalapi.modhandler import Modhandler


PROJECT_ROOT = Path(__file__).parent.parent


def _data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "last.json").write_text(json.dumps({"pedalboard": "/path/to/rig.pedalboard"}))
    return data_dir


def _reset_modhandler_singleton():
    Modhandler._Modhandler__single = None  # pyright: ignore[reportAttributeAccessIssue]


def test_modhandler_init_propagates_ws_bridge_construction_failure(tmp_path):
    _reset_modhandler_singleton()
    data_dir = _data_dir(tmp_path)

    with (
        patch("requests.get"),
        patch("requests.post"),
        patch("pistomp.settings.Settings"),
        patch("modalapi.pedalboard.Pedalboard.load_bundle"),
        patch("modalapi.wifi.WifiManager"),
        patch("subprocess.check_output", return_value=b"SystemState=running"),
        patch("modalapi.modhandler.AsyncWebSocketBridge", side_effect=RuntimeError("bridge boom")),
    ):
        with pytest.raises(RuntimeError, match="bridge boom"):
            Modhandler(MagicMock(), str(PROJECT_ROOT), data_dir=str(data_dir))


def test_modhandler_init_propagates_ws_bridge_start_failure(tmp_path):
    _reset_modhandler_singleton()
    data_dir = _data_dir(tmp_path)

    failing_bridge = MagicMock()
    failing_bridge.start.side_effect = RuntimeError("start boom")

    with (
        patch("requests.get"),
        patch("requests.post"),
        patch("pistomp.settings.Settings"),
        patch("modalapi.pedalboard.Pedalboard.load_bundle"),
        patch("modalapi.wifi.WifiManager"),
        patch("subprocess.check_output", return_value=b"SystemState=running"),
        patch("modalapi.modhandler.AsyncWebSocketBridge", return_value=failing_bridge),
    ):
        with pytest.raises(RuntimeError, match="start boom"):
            Modhandler(MagicMock(), str(PROJECT_ROOT), data_dir=str(data_dir))
