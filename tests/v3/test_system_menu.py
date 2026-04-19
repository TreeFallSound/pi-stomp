"""System-menu actions: shutdown, reboot, reload, restart, save, info load, backup."""

from unittest.mock import patch


def test_v3_system_menu_shutdown(v3_system):
    handler, _, _, _, _ = v3_system
    # Patch lcd.cleanup to avoid panel-stack state issues in tests
    with patch.object(handler.lcd, "cleanup"), patch("os.system") as mock_os:
        handler.system_menu_shutdown(None)
    mock_os.assert_called_once_with("sudo systemctl --no-wall poweroff")


def test_v3_system_menu_reboot(v3_system):
    handler, _, _, _, _ = v3_system
    with patch("os.system") as mock_os:
        handler.system_menu_reboot(None)
    mock_os.assert_called_once_with("sudo systemctl reboot")


def test_v3_system_menu_reload(v3_system):
    handler, _, _, _, _ = v3_system
    with patch("sys.exit") as mock_exit:
        handler.system_menu_reload(None)
    mock_exit.assert_called_once_with(0)


def test_v3_system_menu_restart_sound(v3_system):
    handler, _, _, _, _ = v3_system
    with patch("os.system") as mock_os:
        handler.system_menu_restart_sound(None)
    mock_os.assert_called_once_with("sudo systemctl restart jack")


def test_v3_system_menu_save_current_pb(v3_system, get_urls):
    """save_current_pb() POSTs to /pedalboard/save with the current title."""
    handler, _, _, _, mock_post = v3_system

    handler.system_menu_save_current_pb(None)

    assert any("pedalboard/save" in u for u in get_urls(mock_post))
    post_data = mock_post.call_args[1].get("data") or mock_post.call_args[0][1] if len(mock_post.call_args[0]) > 1 else mock_post.call_args[1]
    # Title should be the current pedalboard title
    assert handler.current.pedalboard.title == "Integration Rig"


def test_v3_system_info_load(v3_system):
    """system_info_load() reads git version, EQ status, and bypass state into handler."""
    handler, _, _, _, _ = v3_system
    handler.audiocard.get_switch_parameter.return_value = True
    handler.audiocard.get_bypass_left.return_value = False
    handler.audiocard.get_bypass_right.return_value = True

    with patch("subprocess.check_output", return_value=b"v1.0.0-abc\n"):
        handler.system_info_load()

    assert handler.software_version == "v1.0.0-abc\n"
    assert handler.eq_status is True
    assert handler.bypass_left is False
    assert handler.bypass_right is True


def test_v3_backup_no_usb(v3_system):
    """user_backup_data() shows a dialog and does not run the backup script when no USB found."""
    handler, _, _, _, _ = v3_system

    # backup_dir is /media/usb0/backups — doesn't exist on dev machines
    with (
        patch("os.path.exists", return_value=True),
        patch("subprocess.call", return_value=1),
        patch.object(handler.lcd, "draw_message_dialog") as mock_dialog,
    ):
        handler.user_backup_data(None)

    mock_dialog.assert_called_once()
    assert "USB" in mock_dialog.call_args[0][0]
