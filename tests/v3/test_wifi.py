"""WiFi polling, hotspot toggle, and credential configuration."""


def test_v3_poll_wifi_update(v3_system, snapshot):
    """poll_wifi() dispatches a wifi update to handler state and redraws the LCD."""
    handler, _, _, _, _ = v3_system
    wifi_status = {"ssid": "TestNet", "signal": -55, "hotspot_active": False}
    handler.wifi_manager.poll.return_value = wifi_status

    handler.poll_wifi()

    assert handler.wifi_status == wifi_status
    snapshot()


def test_v3_poll_wifi_no_update(v3_system):
    """poll_wifi() does nothing when wifi_manager.poll() returns None."""
    handler, _, _, _, _ = v3_system
    handler.wifi_manager.poll.return_value = None
    handler.wifi_status = {}

    handler.poll_wifi()

    assert handler.wifi_status == {}


def test_v3_system_toggle_hotspot_enable(v3_system):
    """system_toggle_hotspot() enables the hotspot when it is currently off."""
    handler, _, _, _, _ = v3_system
    handler.wifi_status = {"hotspot_active": False}

    handler.system_toggle_hotspot()

    handler.wifi_manager.enable_hotspot.assert_called_once()
    handler.wifi_manager.disable_hotspot.assert_not_called()


def test_v3_system_toggle_hotspot_disable(v3_system):
    """system_toggle_hotspot() disables the hotspot when it is currently on."""
    handler, _, _, _, _ = v3_system
    handler.wifi_status = {"hotspot_active": True}

    handler.system_toggle_hotspot()

    handler.wifi_manager.disable_hotspot.assert_called_once()
    handler.wifi_manager.enable_hotspot.assert_not_called()


def test_v3_configure_wifi_credentials(v3_system):
    """configure_wifi_credentials() delegates to wifi_manager.configure_wifi()."""
    handler, _, _, _, _ = v3_system
    handler.wifi_manager.configure_wifi.return_value = True

    result = handler.configure_wifi_credentials("MyNet", "secret")

    handler.wifi_manager.configure_wifi.assert_called_once_with("MyNet", "secret")
    assert result is True
