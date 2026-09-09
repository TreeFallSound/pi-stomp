"""Tap tempo: BPM send, BPM fetch, and tap-tempo-enable toggle."""

from unittest.mock import MagicMock

from tests.types import SystemFixture


def test_set_mod_tap_tempo(modhandler_system: SystemFixture):
    """set_mod_tap_tempo() sends BPM over the WebSocket, not the blocking POST,
    and reports that the value left."""
    handler = modhandler_system.handler
    mock_post = modhandler_system.mock_post

    assert handler.set_mod_tap_tempo(120) is True

    assert "transport-bpm 120" in modhandler_system.ws_bridge.sent
    mock_post.assert_not_called()


def test_set_mod_tap_tempo_reports_failure_when_send_never_leaves(modhandler_system: SystemFixture):
    """A refused send means the value never left — commit relies on this False to
    roll the LCD back."""
    handler = modhandler_system.handler
    modhandler_system.ws_bridge.send_bpm = MagicMock(return_value=False)

    assert handler.set_mod_tap_tempo(120) is False
    modhandler_system.mock_post.assert_not_called()  # no blocking POST fallback ever


def test_set_mod_tap_tempo_refused_during_a_load(modhandler_system: SystemFixture):
    """The load window suppresses BPM like every other parameter. A value that
    slipped through would be overwritten by mod-ui's post-load rebroadcast."""
    handler = modhandler_system.handler
    handler._is_pedalboard_loading = True

    assert handler.set_mod_tap_tempo(120) is False
    assert modhandler_system.ws_bridge.sent == []


def test_set_mod_tap_tempo_none(modhandler_system: SystemFixture):
    """set_mod_tap_tempo(None) is a no-op."""
    handler = modhandler_system.handler
    mock_post = modhandler_system.mock_post
    handler.set_mod_tap_tempo(None)
    mock_post.assert_not_called()


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
