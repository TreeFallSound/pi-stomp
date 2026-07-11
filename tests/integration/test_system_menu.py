"""System-menu actions: shutdown, reboot, reload, restart, save, backup."""

import os
from unittest.mock import patch

from tests.types import SystemFixture


def test_system_menu_shutdown(modhandler_system: SystemFixture):
    handler = modhandler_system.handler
    with patch.object(handler.lcd, "cleanup"), patch("os.system") as mock_os, patch("os._exit") as mock_exit:
        handler.system_menu_shutdown(None)
    mock_os.assert_called_once_with("sudo systemctl --no-wall poweroff")
    mock_exit.assert_called_once_with(0)


def test_system_menu_reboot(modhandler_system: SystemFixture):
    handler = modhandler_system.handler
    with patch("os.system") as mock_os, patch("os._exit") as mock_exit:
        handler.system_menu_reboot(None)
    mock_os.assert_called_once_with("sudo systemctl reboot")
    mock_exit.assert_called_once_with(0)


def test_system_menu_reload(modhandler_system: SystemFixture):
    handler = modhandler_system.handler
    with patch("sys.exit") as mock_exit:
        handler.system_menu_reload(None)
    mock_exit.assert_called_once_with(0)


def test_system_menu_restart_sound(modhandler_system: SystemFixture):
    handler = modhandler_system.handler
    with patch("os.system") as mock_os:
        handler.system_menu_restart_sound(None)
    mock_os.assert_called_once_with("sudo systemctl restart jack")


def test_system_menu_save_current_pb(modhandler_system: SystemFixture, get_urls):
    """save_current_pb() POSTs to /pedalboard/save with the current title."""
    handler = modhandler_system.handler
    mock_post = modhandler_system.mock_post

    handler.system_menu_save_current_pb(None)

    assert any("pedalboard/save" in u for u in get_urls(mock_post))


def test_backup_no_usb(modhandler_system: SystemFixture):
    """user_backup_data() shows a dialog and does not run the backup script when no USB found."""
    handler = modhandler_system.handler
    with (
        patch("os.path.isdir", return_value=False),
        patch.object(handler.lcd, "draw_message_dialog") as mock_dialog,
        patch("subprocess.check_output") as mock_backup,
    ):
        handler.user_backup_data(None)

    mock_dialog.assert_called_once()
    assert "USB" in mock_dialog.call_args[0][0]
    mock_backup.assert_not_called()


def test_check_usb_no_media_dir(modhandler_system: SystemFixture):
    """check_usb() returns [] when /media doesn't exist (no USB automount ever ran)."""
    handler = modhandler_system.handler
    with patch("os.path.isdir", return_value=False):
        assert handler.check_usb() == []


def test_check_usb_finds_mounted_stick(modhandler_system: SystemFixture):
    """check_usb() discovers a stick mounted at /media/<label> and creates its backups dir."""
    handler = modhandler_system.handler
    with (
        patch("os.path.isdir", return_value=True),
        patch("os.listdir", return_value=["MYSTICK"]),
        patch("os.path.ismount", return_value=True),
        patch("os.path.exists", return_value=False),
        patch("os.mkdir") as mock_mkdir,
    ):
        backup_dirs = handler.check_usb()

    assert backup_dirs == [os.path.join("/media", "MYSTICK", "backups")]
    mock_mkdir.assert_called_once_with(backup_dirs[0])


def test_check_usb_ignores_unmounted_media_dirs(modhandler_system: SystemFixture):
    """check_usb() returns [] when /media has stale/empty dirs that aren't actual mountpoints."""
    handler = modhandler_system.handler
    with (
        patch("os.path.isdir", return_value=True),
        patch("os.listdir", return_value=["leftover"]),
        patch("os.path.ismount", return_value=False),
    ):
        assert handler.check_usb() == []


def test_backup_with_usb_runs_script(modhandler_system: SystemFixture):
    """user_backup_data() invokes data-backup.sh with the discovered mount's backups dir."""
    handler = modhandler_system.handler
    with (
        patch.object(handler, "check_usb", return_value=["/media/MYSTICK/backups"]),
        patch("subprocess.check_output") as mock_backup,
        patch.object(handler.lcd, "draw_message_dialog") as mock_dialog,
    ):
        handler.user_backup_data(None)

    args = mock_backup.call_args[0][0]
    assert args[1] == os.path.join("/media/MYSTICK/backups", handler.backup_file)
    mock_dialog.assert_called_once_with("Backup complete", "Info")


class _FakeUsage:
    def __init__(self, total: int):
        self.total = total


def test_backup_with_multiple_usb_shows_selection_menu(modhandler_system: SystemFixture):
    """With several sticks mounted, user_backup_data() lets the user pick one instead of guessing."""
    handler = modhandler_system.handler
    dirs = ["/media/STICK_A/backups", "/media/STICK_B/backups"]
    with (
        patch.object(handler, "check_usb", return_value=dirs),
        patch("shutil.disk_usage", return_value=_FakeUsage(32_000_000_000)),
        patch("subprocess.check_output") as mock_backup,
        patch.object(handler.lcd, "draw_selection_menu") as mock_menu,
    ):
        handler.user_backup_data(None)

    mock_backup.assert_not_called()
    mock_menu.assert_called_once()
    args, kwargs = mock_menu.call_args
    assert args[1] == "Choose USB drive"
    items = args[0]
    assert [label for label, _callback, _arg in items] == ["STICK_A (32.0GB)", "STICK_B (32.0GB)"]

    # Picking the second item runs the backup against that stick's dir.
    _label, callback, arg = items[1]
    with patch("subprocess.check_output") as mock_backup, patch.object(handler.lcd, "draw_message_dialog"):
        callback(arg)
    assert mock_backup.call_args[0][0][1] == os.path.join(dirs[1], handler.backup_file)


def test_restore_only_offers_drives_with_a_backup(modhandler_system: SystemFixture):
    """user_restore_data() skips the menu entirely when only one stick actually has a backup."""
    handler = modhandler_system.handler
    dirs = ["/media/EMPTY_STICK/backups", "/media/HAS_BACKUP/backups"]
    with (
        patch.object(handler, "check_usb", return_value=dirs),
        patch("os.path.exists", side_effect=lambda p: p == os.path.join(dirs[1], handler.backup_file)),
        patch("subprocess.check_output") as mock_restore,
        patch.object(handler.lcd, "draw_selection_menu") as mock_menu,
        patch.object(handler, "system_menu_restart_sound"),
        patch.object(handler.lcd, "draw_message_dialog"),
    ):
        handler.user_restore_data(None)

    mock_menu.assert_not_called()
    assert mock_restore.call_args[0][0][-2] == os.path.join(dirs[1], handler.backup_file)


def test_restore_success_defers_restart_until_ok_pressed(modhandler_system: SystemFixture):
    """A successful restore must not restart anything until the user presses OK — the restart
    cascades (jack -> mod-host -> mod-ui -> pi-stomp), so firing it immediately would tear down
    the process before the user ever sees the confirmation dialog."""
    handler = modhandler_system.handler
    with (
        patch("subprocess.check_output", return_value=b""),
        patch.object(handler.lcd, "draw_message_dialog") as mock_dialog,
        patch.object(handler, "system_menu_restart_sound") as mock_restart,
    ):
        handler._do_restore_data("/media/MYSTICK/backups")

        mock_restart.assert_not_called()
        assert "OK" in mock_dialog.call_args[0][0]

        on_dismiss = mock_dialog.call_args.kwargs["on_dismiss"]
        on_dismiss()

    mock_restart.assert_called_once_with(None)


def test_restore_with_no_backups_shows_no_usb_dialog(modhandler_system: SystemFixture):
    """user_restore_data() reports no USB device when sticks are mounted but none has a backup."""
    handler = modhandler_system.handler
    dirs = ["/media/EMPTY_A/backups", "/media/EMPTY_B/backups"]
    with (
        patch.object(handler, "check_usb", return_value=dirs),
        patch("os.path.exists", return_value=False),
        patch.object(handler.lcd, "draw_message_dialog") as mock_dialog,
    ):
        handler.user_restore_data(None)

    mock_dialog.assert_called_once()
    assert "USB" in mock_dialog.call_args[0][0]
