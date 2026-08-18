"""Startup failure modes and recovery paths."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import common.token as Token
from modalapi.pedalboard_monitor import write_last_json

with patch("pistomp.settings.Settings.load_settings"), patch("pistomp.settings.Settings.set_setting"):
    from modalapi.modhandler import Modhandler, STARTUP_REST_BACKOFF_S


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
        patch("pistomp.httpclient.get"),
        patch("pistomp.httpclient.post"),
        patch("pistomp.settings.Settings"),
        patch("modalapi.pedalboard.Pedalboard.hydrate"),
        patch("modalapi.wifi.WifiManager"),
        patch("subprocess.check_output", return_value=b"SystemState=running"),
        patch("modalapi.modhandler.AsyncWebSocketBridge", side_effect=RuntimeError("bridge boom")),
    ):
        with pytest.raises(RuntimeError, match="bridge boom"):
            Modhandler(MagicMock(), str(PROJECT_ROOT), data_dir=str(data_dir))


def test_missing_last_json_recovery(tmp_path):
    """Missing last.json: startup writes it with the first pedalboard and sets handler.current."""
    _reset_modhandler_singleton()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # Intentionally no last.json

    with (
        patch("pistomp.httpclient.get") as mock_get,
        patch("pistomp.httpclient.post") as mock_post,
        patch("pistomp.settings.Settings"),
        patch("modalapi.pedalboard.Pedalboard.hydrate"),
        patch("modalapi.wifi.WifiManager"),
        patch("subprocess.check_output", return_value=b"SystemState=running"),
        patch("modalapi.modhandler.AsyncWebSocketBridge", return_value=MagicMock()),
    ):

        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = (
                json.dumps(
                    [
                        {Token.TITLE: "First Rig", Token.BUNDLE: "/path/to/first.pedalboard"},
                        {Token.TITLE: "Second Rig", Token.BUNDLE: "/path/to/second.pedalboard"},
                    ]
                )
                if "pedalboard/list" in url
                else json.dumps({"0": "Default"})
                if "snapshot/list" in url
                else "{}"
            )
            return resp

        mock_get.side_effect = get_side_effect
        mock_post.return_value = MagicMock(status_code=200, text="{}")

        handler = Modhandler(MagicMock(), str(PROJECT_ROOT), data_dir=str(data_dir))
        handler.settings = MagicMock()
        handler.settings.get_setting.return_value = None
        handler.add_hardware(MagicMock())
        handler.add_lcd(MagicMock())
        handler.load_pedalboards()

        # Precondition: last.json absent → None
        assert handler.get_current_pedalboard_bundle_path() is None
        assert handler.pedalboard_list

        # Recovery sequence (mirrors modalapistomp.py startup branch)
        pb = handler.pedalboard_list[0]
        write_last_json(handler.last_json_monitor.path, pb.bundle)
        handler.pedalboard_change(pb)
        handler.set_current_pedalboard(pb)

        # last.json written with the first pedalboard
        last = json.loads((data_dir / "last.json").read_text())
        assert last["pedalboard"] == "/path/to/first.pedalboard"
        assert last["bank"] == -2

        # handler.current is set and points to the right pedalboard
        assert handler.current is not None
        assert handler.current.pedalboard.bundle == "/path/to/first.pedalboard"

        # mod-ui received a load_bundle POST for the first pedalboard
        post_urls = [c.args[0] for c in mock_post.call_args_list]
        assert any("load_bundle" in u for u in post_urls)


def _pedalboard_list_response():
    resp = MagicMock()
    resp.status_code = 200
    resp.text = json.dumps([{Token.TITLE: "First Rig", Token.BUNDLE: "/path/to/first.pedalboard"}])
    return resp


def test_load_pedalboards_waits_for_cold_mod_ui(tmp_path):
    """mod-ui is 'started' before it binds its port; refusals must be retried, not fatal."""
    _reset_modhandler_singleton()
    data_dir = _data_dir(tmp_path)

    with (
        patch("pistomp.httpclient.get") as mock_get,
        patch("pistomp.httpclient.post", return_value=MagicMock(status_code=200, text="{}")),
        patch("pistomp.settings.Settings"),
        patch("modalapi.pedalboard.Pedalboard.hydrate"),
        patch("modalapi.wifi.WifiManager"),
        patch("subprocess.check_output", return_value=b"SystemState=running"),
        patch("modalapi.modhandler.AsyncWebSocketBridge", return_value=MagicMock()),
        patch("modalapi.modhandler.time.sleep") as mock_sleep,
    ):
        mock_get.return_value = MagicMock(status_code=200, text="{}")
        handler = Modhandler(MagicMock(), str(PROJECT_ROOT), data_dir=str(data_dir))

        # Refused twice, then mod-ui finishes its LV2 scan and answers.
        calls = {"n": 0}

        def get_side_effect(url, **kwargs):
            if "pedalboard/list" not in url:
                return MagicMock(status_code=200, text="{}")
            calls["n"] += 1
            if calls["n"] <= 2:
                raise ConnectionRefusedError(111, "Connection refused")
            return _pedalboard_list_response()

        mock_get.side_effect = get_side_effect

        handler.load_pedalboards()

        assert calls["n"] == 3
        assert [pb.bundle for pb in handler.pedalboard_list] == ["/path/to/first.pedalboard"]
        # Front-loaded backoff: two refusals cost 0.5s, not 2s.
        assert [c.args[0] for c in mock_sleep.call_args_list] == [0.25, 0.25]


def test_load_pedalboards_still_exits_when_mod_ui_never_comes_up(tmp_path):
    """The retry budget is bounded — a genuinely dead mod-ui must still fail fast."""
    _reset_modhandler_singleton()
    data_dir = _data_dir(tmp_path)

    with (
        patch("pistomp.httpclient.get") as mock_get,
        patch("pistomp.httpclient.post", return_value=MagicMock(status_code=200, text="{}")),
        patch("pistomp.settings.Settings"),
        patch("modalapi.pedalboard.Pedalboard.hydrate"),
        patch("modalapi.wifi.WifiManager"),
        patch("subprocess.check_output", return_value=b"SystemState=running"),
        patch("modalapi.modhandler.AsyncWebSocketBridge", return_value=MagicMock()),
        patch("modalapi.modhandler.time.sleep") as mock_sleep,
    ):
        mock_get.return_value = MagicMock(status_code=200, text="{}")
        handler = Modhandler(MagicMock(), str(PROJECT_ROOT), data_dir=str(data_dir))

        attempts = {"n": 0}

        def get_side_effect(url, **kwargs):
            if "pedalboard/list" not in url:
                return MagicMock(status_code=200, text="{}")
            attempts["n"] += 1
            raise ConnectionRefusedError(111, "Connection refused")

        mock_get.side_effect = get_side_effect

        with pytest.raises(SystemExit):
            handler.load_pedalboards()

        assert attempts["n"] == len(STARTUP_REST_BACKOFF_S) + 1
        assert [c.args[0] for c in mock_sleep.call_args_list] == list(STARTUP_REST_BACKOFF_S)
        assert sum(STARTUP_REST_BACKOFF_S) == 4.0


def test_modhandler_init_propagates_ws_bridge_start_failure(tmp_path):
    _reset_modhandler_singleton()
    data_dir = _data_dir(tmp_path)

    failing_bridge = MagicMock()
    failing_bridge.start.side_effect = RuntimeError("start boom")

    with (
        patch("pistomp.httpclient.get"),
        patch("pistomp.httpclient.post"),
        patch("pistomp.settings.Settings"),
        patch("modalapi.pedalboard.Pedalboard.hydrate"),
        patch("modalapi.wifi.WifiManager"),
        patch("subprocess.check_output", return_value=b"SystemState=running"),
        patch("modalapi.modhandler.AsyncWebSocketBridge", return_value=failing_bridge),
    ):
        with pytest.raises(RuntimeError, match="start boom"):
            Modhandler(MagicMock(), str(PROJECT_ROOT), data_dir=str(data_dir))
