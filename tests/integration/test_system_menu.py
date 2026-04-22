"""System-menu actions: shutdown, reboot, reload, restart, save, backup."""

from unittest.mock import patch

from tests.types import SystemFixture


def test_system_menu_shutdown(modhandler_system: SystemFixture):
    handler, _, _, _, _ = modhandler_system
    with patch.object(handler.lcd, "cleanup"), patch("os.system") as mock_os:
        handler.system_menu_shutdown(None)
    mock_os.assert_called_once_with("sudo systemctl --no-wall poweroff")


def test_system_menu_reboot(modhandler_system: SystemFixture):
    handler, _, _, _, _ = modhandler_system
    with patch("os.system") as mock_os:
        handler.system_menu_reboot(None)
    mock_os.assert_called_once_with("sudo systemctl reboot")


def test_system_menu_reload(modhandler_system: SystemFixture):
    handler, _, _, _, _ = modhandler_system
    with patch("sys.exit") as mock_exit:
        handler.system_menu_reload(None)
    mock_exit.assert_called_once_with(0)


def test_system_menu_restart_sound(modhandler_system: SystemFixture):
    handler, _, _, _, _ = modhandler_system
    with patch("os.system") as mock_os:
        handler.system_menu_restart_sound(None)
    mock_os.assert_called_once_with("sudo systemctl restart jack")


def test_system_menu_save_current_pb(modhandler_system: SystemFixture, get_urls):
    """save_current_pb() POSTs to /pedalboard/save with the current title."""
    handler, _, _, _, mock_post = modhandler_system

    handler.system_menu_save_current_pb(None)

    assert any("pedalboard/save" in u for u in get_urls(mock_post))


def test_backup_no_usb(modhandler_system: SystemFixture):
    """user_backup_data() shows a dialog and does not run the backup script when no USB found."""
    handler, _, _, _, _ = modhandler_system
    with (
        patch("os.path.exists", return_value=True),
        patch("subprocess.call", return_value=1),
        patch.object(handler.lcd, "draw_message_dialog") as mock_dialog,
    ):
        handler.user_backup_data(None)

    mock_dialog.assert_called_once()
    assert "USB" in mock_dialog.call_args[0][0]
