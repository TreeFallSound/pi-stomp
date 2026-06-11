"""Tap tempo: BPM send, BPM fetch, and tap-tempo-enable toggle."""

from unittest.mock import MagicMock

from tests.types import SystemFixture


def test_set_mod_tap_tempo(modhandler_system: SystemFixture):
    """set_mod_tap_tempo() POSTs to /set_bpm with the BPM value."""
    handler = modhandler_system.handler
    mock_post = modhandler_system.mock_post

    handler.set_mod_tap_tempo(120)

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "set_bpm" in call_args.args[0]
    assert call_args.kwargs.get("json", {}).get("value") == 120


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
