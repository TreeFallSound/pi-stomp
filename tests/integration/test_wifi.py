# pyright: reportAttributeAccessIssue=false
"""WiFi polling, hotspot toggle, and credential configuration."""

from tests.types import SystemFixture


def test_poll_wifi_update(modhandler_system: SystemFixture):
    """poll_wifi() dispatches a wifi update to handler state."""
    handler, _, _, _, _ = modhandler_system

    assert handler.wifi_manager

    wifi_status = {"ssid": "TestNet", "signal": -55, "hotspot_active": False}
    handler.wifi_manager.poll.return_value = wifi_status

    handler.poll_wifi()

    assert handler.wifi_status == wifi_status


def test_poll_wifi_no_update(modhandler_system: SystemFixture):
    """poll_wifi() does nothing when wifi_manager.poll() returns None."""
    handler, _, _, _, _ = modhandler_system

    assert handler.wifi_manager

    handler.wifi_manager.poll.return_value = None
    handler.wifi_status = {}

    handler.poll_wifi()

    assert handler.wifi_status == {}


def test_system_toggle_hotspot_enable(modhandler_system: SystemFixture):
    handler, _, _, _, _ = modhandler_system

    assert handler.wifi_manager

    handler.wifi_status = {"hotspot_active": False}
    handler.system_toggle_hotspot()
    handler.wifi_manager.enable_hotspot.assert_called_once()
    handler.wifi_manager.disable_hotspot.assert_not_called()


def test_system_toggle_hotspot_disable(modhandler_system: SystemFixture):
    handler, _, _, _, _ = modhandler_system

    assert handler.wifi_manager

    handler.wifi_status = {"hotspot_active": True}
    handler.system_toggle_hotspot()
    handler.wifi_manager.disable_hotspot.assert_called_once()
    handler.wifi_manager.enable_hotspot.assert_not_called()


def test_configure_wifi_credentials(modhandler_system: SystemFixture):
    handler, _, _, _, _ = modhandler_system

    assert handler.wifi_manager

    handler.wifi_manager.configure_wifi.return_value = True
    result = handler.configure_wifi_credentials("MyNet", "secret")
    handler.wifi_manager.configure_wifi.assert_called_once_with("MyNet", "secret")
    assert result is True
