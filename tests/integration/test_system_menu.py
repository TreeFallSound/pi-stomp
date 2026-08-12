"""System-menu actions: shutdown, reboot, reload, restart, save, backup."""

import os
from unittest.mock import patch

from modalapi.archive import JobState
from tests.archive_fake import fake_jobs
from tests.types import SystemFixture
from ui.archive_panel import ArchiveProgressPanel


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


def test_backup_with_usb_starts_job_behind_progress_panel(modhandler_system: SystemFixture):
    """user_backup_data() starts the job against the discovered mount and shows progress
    rather than blocking the UI thread until zip finishes."""
    handler = modhandler_system.handler
    with (
        patch.object(handler, "check_usb", return_value=["/media/MYSTICK/backups"]),
        fake_jobs() as jobs,
    ):
        handler.user_backup_data(None)

    assert jobs[0].argv[1] == os.path.join("/media/MYSTICK/backups", handler.backup_file)
    assert handler.lcd.pstack.find_panel_type(ArchiveProgressPanel) is not None


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
        fake_jobs() as jobs,
        patch.object(handler.lcd, "draw_selection_menu") as mock_menu,
    ):
        handler.user_backup_data(None)

    assert jobs == []
    mock_menu.assert_called_once()
    args, kwargs = mock_menu.call_args
    assert args[1] == "Choose USB drive"
    items = args[0]
    assert [label for label, _callback, _arg in items] == ["STICK_A (32.0GB)", "STICK_B (32.0GB)"]

    # Picking the second item runs the backup against that stick's dir.
    _label, callback, arg = items[1]
    with fake_jobs() as jobs:
        callback(arg)
    assert jobs[0].argv[1] == os.path.join(dirs[1], handler.backup_file)


def test_restore_only_offers_drives_with_a_backup(modhandler_system: SystemFixture):
    """user_restore_data() skips the menu entirely when only one stick actually has a backup."""
    handler = modhandler_system.handler
    dirs = ["/media/EMPTY_STICK/backups", "/media/HAS_BACKUP/backups"]
    with (
        patch.object(handler, "check_usb", return_value=dirs),
        patch("os.path.exists", side_effect=lambda p: p == os.path.join(dirs[1], handler.backup_file)),
        fake_jobs() as jobs,
        patch.object(handler.lcd, "draw_selection_menu") as mock_menu,
        patch.object(handler, "restart_ui_stack"),
    ):
        handler.user_restore_data(None)

    mock_menu.assert_not_called()
    assert jobs[0].argv[-2] == os.path.join(dirs[1], handler.backup_file)


def test_restore_defers_restart_until_the_button_is_pressed(modhandler_system: SystemFixture):
    """A successful restore must not restart anything on its own — the restart cascades
    (jack -> mod-host -> mod-ui -> pi-stomp), so firing it the moment unzip exits would tear
    the process down under the user. The button press is the consent; there is no dialog."""
    handler = modhandler_system.handler
    with (
        fake_jobs() as jobs,
        patch.object(handler.lcd, "draw_message_dialog") as mock_dialog,
        patch.object(handler, "restart_ui_stack") as mock_restart,
    ):
        handler._do_restore_data("/media/MYSTICK/backups")
        panel = handler.lcd.pstack.find_panel_type(ArchiveProgressPanel)
        assert panel is not None

        jobs[0].finish(JobState.DONE)
        panel.tick()
        mock_restart.assert_not_called()
        assert panel._btn.text == "Restart to continue"

        panel._on_button()

    mock_restart.assert_called_once_with()
    mock_dialog.assert_not_called()


def test_failed_restore_offers_close_and_never_restarts(modhandler_system: SystemFixture):
    """A restore that failed leaves data/ half-written; restarting into that is worse than
    staying put, so the terminal button must not invite it."""
    handler = modhandler_system.handler
    with (
        fake_jobs() as jobs,
        patch.object(handler, "restart_ui_stack") as mock_restart,
    ):
        handler._do_restore_data("/media/MYSTICK/backups")
        panel = handler.lcd.pstack.find_panel_type(ArchiveProgressPanel)
        assert panel is not None

        jobs[0].finish(JobState.FAILED, error="unzip: cannot find zipfile directory")
        panel.tick()
        assert panel._btn.text == "Close"

        panel._on_button()

    mock_restart.assert_not_called()


def test_backup_completion_shows_no_dialog(modhandler_system: SystemFixture):
    """Backup reports success in the panel itself — no popup to dismiss afterwards."""
    handler = modhandler_system.handler
    with (
        patch.object(handler, "check_usb", return_value=["/media/MYSTICK/backups"]),
        fake_jobs() as jobs,
        patch.object(handler.lcd, "draw_message_dialog") as mock_dialog,
    ):
        handler.user_backup_data(None)
        panel = handler.lcd.pstack.find_panel_type(ArchiveProgressPanel)
        assert panel is not None

        jobs[0].finish(JobState.DONE)
        panel.tick()
        assert panel._btn.text == "Close"
        panel._on_button()

    mock_dialog.assert_not_called()
    assert handler.lcd.pstack.find_panel_type(ArchiveProgressPanel) is None


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


def test_drive_detail_reports_free_space(modhandler_system: SystemFixture):
    """The backup subtitle names the drive and how much room is left on it."""
    handler = modhandler_system.handler

    class _Usage:
        total = 58_000_000_000
        free = 57_000_000_000

    with patch("shutil.disk_usage", return_value=_Usage()):
        assert handler._drive_detail("/media/STAGE_LEFT/backups") == "STAGE_LEFT · 57.0GB free of 58.0GB"


def test_drive_detail_falls_back_to_name_when_unreadable(modhandler_system: SystemFixture):
    """A stick yanked between menu and panel must not take the panel down with it."""
    handler = modhandler_system.handler
    with patch("shutil.disk_usage", side_effect=OSError):
        assert handler._drive_detail("/media/GONE/backups") == "GONE"


def test_archive_detail_reports_size_and_age(modhandler_system: SystemFixture):
    """Restore overwrites data/, so the subtitle says which vintage is about to land."""
    handler = modhandler_system.handler

    class _Stat:
        st_size = 344_307_247
        st_mtime = 1_754_942_700.0  # 2025-08-11 18:45 local

    with patch("os.stat", return_value=_Stat()):
        detail = handler._archive_detail("/media/STAGE_LEFT/backups")

    assert detail.startswith("STAGE_LEFT · 344.3MB from ")


def test_archive_detail_falls_back_to_name_when_missing(modhandler_system: SystemFixture):
    handler = modhandler_system.handler
    with patch("os.stat", side_effect=OSError):
        assert handler._archive_detail("/media/GONE/backups") == "GONE"


def test_restart_ui_stack_is_non_blocking_and_skips_jack(modhandler_system: SystemFixture):
    """Restoring data/ invalidates what mod-ui and pi-stomp cache, not the audio engine.
    Restarting jack would drag six other units down with it, and os.system would block the
    10ms loop while waiting on the restart that kills this very process."""
    handler = modhandler_system.handler
    with patch("subprocess.Popen") as mock_popen:
        handler.restart_ui_stack()

    argv = mock_popen.call_args[0][0]
    assert argv == ["sudo", "systemctl", "--no-block", "restart", "mod-ui"]
