"""Tap tempo: BPM send, BPM fetch, and tap-tempo-enable toggle."""

from unittest.mock import MagicMock

from tests.types import SystemFixture


def test_set_mod_tap_tempo(modhandler_system: SystemFixture):
    """set_mod_tap_tempo() sends the BPM via the ws_bridge."""
    handler = modhandler_system.handler
    ws_bridge = modhandler_system.ws_bridge

    handler.set_mod_tap_tempo(120)

    assert "transport-bpm 120" in ws_bridge.sent


def test_set_mod_tap_tempo_none(modhandler_system: SystemFixture):
    """set_mod_tap_tempo(None) is a no-op."""
    handler = modhandler_system.handler
    ws_bridge = modhandler_system.ws_bridge
    handler.set_mod_tap_tempo(None)
    assert not any(m.startswith("transport-bpm") for m in ws_bridge.sent)


def test_get_bpm(modhandler_system: SystemFixture, get_urls):
    """get_bpm() GETs /get_bpm and returns the parsed float."""
    handler = modhandler_system.handler
    mock_get = modhandler_system.mock_get

    def get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "120.0" if "get_bpm" in url else "{}"
        return resp

    mock_get.side_effect = get_side_effect

    assert handler.get_bpm() == 120.0
    assert any("get_bpm" in u for u in get_urls(mock_get))


def test_toggle_tap_tempo_enable(modhandler_system: SystemFixture):
    """toggle_tap_tempo_enable() calls hardware and updates the LCD footswitches."""
    handler = modhandler_system.handler
    mock_get = modhandler_system.mock_get

    def get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "100.0" if "get_bpm" in url else "{}"
        return resp

    mock_get.side_effect = get_side_effect
    handler.toggle_tap_tempo_enable()


def test_system_menu_bpm_opens_dialog(modhandler_system: SystemFixture):
    """system_menu_bpm() opens a Parameterdialog with the current BPM."""
    handler = modhandler_system.handler
    mock_get = modhandler_system.mock_get

    def get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "120.0" if "get_bpm" in url else "{}"
        return resp

    mock_get.side_effect = get_side_effect

    # Trigger system menu BPM action
    handler.system_menu_bpm(None)

    # Verify the dialog is opened on the display stack and has correct parameter value
    dialog = handler.lcd.w_parameter_dialogs.get("bpm")
    assert dialog is not None
    assert dialog.param_value == 120.0
    assert dialog.param_min == 40.0
    assert dialog.param_max == 240.0
    assert dialog.step == 1.0


def test_system_menu_bpm_commits(modhandler_system: SystemFixture):
    """bpm_commit_callback() sends the updated BPM value to ws_bridge and sets local hardware BPM."""
    handler = modhandler_system.handler
    ws_bridge = modhandler_system.ws_bridge

    handler.bpm_commit_callback("bpm", 135.0)

    assert "transport-bpm 135.0" in ws_bridge.sent
    assert handler.hardware.taptempo.get_bpm() == 135.0


def test_ws_bpm_gating(modhandler_system: SystemFixture):
    """WebSocket TransportMessage updates are ignored for 500ms after manual set_mod_tap_tempo."""
    handler = modhandler_system.handler
    from modalapi.ws_protocol import TransportMessage
    import time

    # Initially, local hardware BPM can be updated via WS
    handler.hardware.taptempo.set_bpm(100.0)
    handler._handle_ws_message(TransportMessage(rolling=True, bpm=120.0))
    assert handler.hardware.taptempo.get_bpm() == 120.0

    # User manually edits BPM, setting the timestamp gate
    handler.set_mod_tap_tempo(130.0)

    # Inbound WebSocket message with different BPM should be ignored during the gate
    handler._handle_ws_message(TransportMessage(rolling=True, bpm=140.0))
    assert handler.hardware.taptempo.get_bpm() == 120.0  # Ignored!

    # Simulate 600ms passing
    handler._last_bpm_change_time = time.time() - 0.6

    # Inbound WebSocket message should now be accepted
    handler._handle_ws_message(TransportMessage(rolling=True, bpm=140.0))
    assert handler.hardware.taptempo.get_bpm() == 140.0


def test_legacy_set_mod_tap_tempo_exception_handling():
    """Legacy Mod.set_mod_tap_tempo handles connection exceptions gracefully."""
    from modalapi.mod import Mod
    from unittest.mock import patch, MagicMock

    Mod._Mod__single = None
    mock_audiocard = MagicMock()
    with patch("requests.post", side_effect=Exception("Connection refused")), patch("pistomp.settings.Settings.load_settings"):
        handler = Mod(mock_audiocard, "/tmp")
        handler.root_uri = "http://localhost:80/"
        # Should not raise exception
        handler.set_mod_tap_tempo(120.0)


def test_legacy_bpm_parameter_tweak_step():
    """Legacy Mod.parameter_value_change uses a tweak size of 1.0 for the bpm symbol."""
    from modalapi.mod import Mod
    from unittest.mock import patch, MagicMock
    from common.parameter import Parameter

    Mod._Mod__single = None
    mock_audiocard = MagicMock()
    with patch("pistomp.settings.Settings.load_settings"):
        handler = Mod(mock_audiocard, "/tmp")
        handler.deep = MagicMock()
        handler.lcd = MagicMock()
        
        # Configure a mock parameter representing BPM
        info = {"shortName": "BPM", "symbol": "bpm", "ranges": {"minimum": 40.0, "maximum": 240.0}}
        param = Parameter(info, 120.0, None)
        handler.deep.selected_parameter = param
        
        # Simulate encoder increment (direction=1)
        commit_mock = MagicMock()
        handler.parameter_value_change(1, commit_mock)
        assert handler.deep.selected_parameter.value == 121.0
        commit_mock.assert_called_once()


def test_lcd_bpm_widget_presence_and_updates(modhandler_system: SystemFixture):
    """LCD w_bpm widget is created, updates on change, and triggers system_menu_bpm on click."""
    handler = modhandler_system.handler
    lcd = handler.lcd

    # w_bpm should be present on color LCD (v2/v3)
    if hasattr(lcd, "w_bpm") and lcd.w_bpm is not None:
        # Check initial value
        assert "BPM" in lcd.w_bpm.text
        
        # Check update_bpm
        lcd.update_bpm(145.2)
        assert lcd.w_bpm.text == "145 BPM"
        
        # Check click action triggers system_menu_bpm
        from unittest.mock import patch
        with patch.object(handler, "system_menu_bpm") as mock_menu:
            from uilib.misc import InputEvent
            lcd.w_bpm.action(InputEvent.CLICK, lcd.w_bpm)
            mock_menu.assert_called_once_with(None)

        # Check info message hides/shows w_bpm
        lcd.draw_info_message("Loading...")
        assert lcd.w_bpm.visible is False
        lcd.draw_info_message("")
        assert lcd.w_bpm.visible is True


def test_parameter_dialog_bpm_rounding():
    """Parameterdialog formats BPM parameter values using round(), and non-BPM using format_float."""
    from uilib.parameterdialog import Parameterdialog
    from unittest.mock import MagicMock

    mock_stack = MagicMock()
    
    # 1. BPM Parameter (should round)
    dialog_bpm = Parameterdialog(
        stack=mock_stack,
        param_name="BPM",
        param_value=128.6,
        param_min=40.0,
        param_max=240.0,
        width=240,
        height=120,
        title="BPM Edit"
    )
    assert dialog_bpm.w_value.text == "129"

    # 2. Non-BPM Parameter (should format with format_float, which truncates > 10)
    dialog_other = Parameterdialog(
        stack=mock_stack,
        param_name="Gain",
        param_value=12.8,
        param_min=0.0,
        param_max=20.0,
        width=240,
        height=120,
        title="Gain Edit"
    )
    assert dialog_other.w_value.text == "12"


def test_websocket_bridge_is_connected_version_agnostic():
    """AsyncWebSocketBridge.is_connected handles websockets v13-v16 (.state) and legacy (.closed)."""
    from modalapi.websocket_bridge import AsyncWebSocketBridge
    from unittest.mock import MagicMock

    bridge = AsyncWebSocketBridge()
    
    # Case 1: ws is None
    bridge._worker.ws = None
    assert bridge.is_connected is False

    # Case 2: Modern websockets connection (v13–v16) with .state
    mock_ws_modern = MagicMock()
    del mock_ws_modern.closed  # Ensure no .closed attribute
    mock_ws_modern.state.name = "OPEN"
    bridge._worker.ws = mock_ws_modern
    assert bridge.is_connected is True

    mock_ws_modern.state.name = "CLOSED"
    assert bridge.is_connected is False

    # Case 3: Legacy websockets connection (with .closed)
    mock_ws_legacy = MagicMock()
    del mock_ws_legacy.state  # Ensure no .state attribute
    mock_ws_legacy.closed = False
    bridge._worker.ws = mock_ws_legacy
    assert bridge.is_connected is True

    mock_ws_legacy.closed = True
    assert bridge.is_connected is False


def test_set_mod_tap_tempo_rest_fallback(modhandler_system: SystemFixture):
    """set_mod_tap_tempo() falls back to REST when WebSocket bridge is disconnected."""
    handler = modhandler_system.handler
    ws_bridge = modhandler_system.ws_bridge
    mock_post = modhandler_system.mock_post

    # Simulate disconnected WebSocket bridge
    ws_bridge.is_connected = False

    handler.set_mod_tap_tempo(120)

    # Should NOT have sent via WebSocket
    assert not any(m.startswith("transport-bpm") for m in ws_bridge.sent)

    # Should have fallen back to REST
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "set_bpm" in call_args.args[0]
    assert call_args.kwargs.get("json", {}).get("value") == 120
