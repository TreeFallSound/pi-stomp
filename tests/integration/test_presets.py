"""Preset management — pure handler logic, no hardware-specific navigation."""

from tests.types import SystemFixture


def test_preset_incr_and_change(modhandler_system: SystemFixture, get_urls):
    """preset_incr_and_change() advances from index 0 → 1."""
    handler, _, _, mock_get, _ = modhandler_system

    handler.preset_incr_and_change()

    assert handler.current
    assert any("snapshot/load?id=1" in u for u in get_urls(mock_get))
    assert handler.current.preset_index == 1


def test_preset_set_and_change(modhandler_system: SystemFixture, get_urls):
    """preset_set_and_change(1) loads snapshot index 1 directly."""
    handler, _, _, mock_get, _ = modhandler_system

    handler.preset_set_and_change(1)

    assert any("snapshot/load?id=1" in u for u in get_urls(mock_get))


def test_preset_change_out_of_range(modhandler_system: SystemFixture, get_urls):
    """preset_change() with an invalid index shows a dialog and makes no HTTP call."""
    handler, _, _, mock_get, _ = modhandler_system

    handler.preset_change(99)

    assert not any("snapshot/load" in u for u in get_urls(mock_get))
