"""Tap tempo: BPM send, BPM fetch, and tap-tempo-enable toggle."""

from unittest.mock import MagicMock


def test_v3_set_mod_tap_tempo(v3_system, get_urls):
    """set_mod_tap_tempo() POSTs the BPM value to /set_bpm."""
    handler, _, _, _, mock_post = v3_system

    handler.set_mod_tap_tempo(120)

    assert any("set_bpm" in u for u in get_urls(mock_post))
    payload = mock_post.call_args[1].get("json") or mock_post.call_args[0][1]
    assert payload == {"value": 120}


def test_v3_set_mod_tap_tempo_none(v3_system, get_urls):
    """set_mod_tap_tempo(None) is a no-op — no HTTP call."""
    handler, _, _, _, mock_post = v3_system

    handler.set_mod_tap_tempo(None)

    assert not any("set_bpm" in u for u in get_urls(mock_post))


def test_v3_get_bpm(v3_system, get_urls):
    """get_bpm() GETs /get_bpm and returns the parsed float."""
    handler, _, _, mock_get, _ = v3_system

    def get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "120.0" if "get_bpm" in url else "{}"
        return resp

    mock_get.side_effect = get_side_effect

    result = handler.get_bpm()

    assert any("get_bpm" in u for u in get_urls(mock_get))
    assert result == 120.0


def test_v3_toggle_tap_tempo_enable(v3_system, snapshot):
    """toggle_tap_tempo_enable() calls hardware and updates the LCD footswitches."""
    handler, hw, _, mock_get, _ = v3_system

    def get_side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "100.0" if "get_bpm" in url else "{}"
        return resp

    mock_get.side_effect = get_side_effect

    handler.toggle_tap_tempo_enable()

    snapshot()
