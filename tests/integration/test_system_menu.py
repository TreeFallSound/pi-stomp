"""System-menu actions: shutdown, reboot, reload, restart, save, backup, sync."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from pistomp.sync import PedalboardSync, SyncResult
from tests.types import SystemFixture


def test_system_menu_shutdown(modhandler_system: SystemFixture):
    handler = modhandler_system.handler
    with patch.object(handler.lcd, "cleanup"), patch("os.system") as mock_os:
        handler.system_menu_shutdown(None)
    mock_os.assert_called_once_with("sudo systemctl --no-wall poweroff")


def test_system_menu_reboot(modhandler_system: SystemFixture):
    handler = modhandler_system.handler
    with patch("os.system") as mock_os:
        handler.system_menu_reboot(None)
    mock_os.assert_called_once_with("sudo systemctl reboot")


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
        patch("os.path.exists", return_value=True),
        patch("subprocess.call", return_value=1),
        patch.object(handler.lcd, "draw_message_dialog") as mock_dialog,
    ):
        handler.user_backup_data(None)

    mock_dialog.assert_called_once()
    assert "USB" in mock_dialog.call_args[0][0]


# ---------------------------------------------------------------------------
# system_menu_sync_pedalboards
# ---------------------------------------------------------------------------

def _run_sync(modhandler_system: SystemFixture, returncode: int, stdout: str) -> SyncResult:
    handler = modhandler_system.handler
    completed = subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")
    with patch("subprocess.run", return_value=completed):
        return handler.system_menu_sync_pedalboards()


def test_sync_up_to_date(modhandler_system: SystemFixture):
    result = _run_sync(modhandler_system, 0, "Already up to date")
    assert result.status == "up_to_date"


def test_sync_applied(modhandler_system: SystemFixture):
    result = _run_sync(modhandler_system, 0, "2 update(s) applied")
    assert result.status == "applied"
    assert result.count == 2


def test_sync_network_error(modhandler_system: SystemFixture):
    result = _run_sync(modhandler_system, 2, "network: timeout")
    assert result.status == "network_error"


def test_sync_conflicts(modhandler_system: SystemFixture):
    stdout = "Metal.pedalboard/config.yml\nConflicts: resolve via SSH ..."
    result = _run_sync(modhandler_system, 3, stdout)
    assert result.status == "conflicts"
    assert result.conflicts == ["Metal.pedalboard/config.yml"]


def test_sync_error(modhandler_system: SystemFixture):
    result = _run_sync(modhandler_system, 1, "fatal: something broke")
    assert result.status == "error"


def test_sync_uses_data_dir(modhandler_system: SystemFixture):
    """PedalboardSync is given data_dir/.pedalboards as the target directory."""
    handler = modhandler_system.handler
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="Already up to date", stderr="")
    with patch("subprocess.run", return_value=completed) as mock_run:
        handler.system_menu_sync_pedalboards()

    cmd = mock_run.call_args[0][0]
    expected_dir = str(Path(handler.data_dir) / ".pedalboards")
    assert cmd[-1] == expected_dir


# ---------------------------------------------------------------------------
# init_pedalboards_remote
# ---------------------------------------------------------------------------


def test_init_pedalboards_remote_stores_url(modhandler_system: SystemFixture):
    handler = modhandler_system.handler
    with patch.object(PedalboardSync, "configure_remote", return_value=SyncResult(status="up_to_date", message="Up to date")):
        handler.init_pedalboards_remote("https://example.com/pb.git")
    assert handler.pedalboards_remote == "https://example.com/pb.git"


def test_init_pedalboards_remote_clears_notification_on_success(modhandler_system: SystemFixture):
    handler = modhandler_system.handler
    handler.set_notification("stale notification")
    with patch.object(PedalboardSync, "configure_remote", return_value=SyncResult(status="applied", count=1, message="1 update(s) applied")):
        handler.init_pedalboards_remote("https://example.com/pb.git")
    assert handler.notification is None


def test_init_pedalboards_remote_sets_notification_on_error(modhandler_system: SystemFixture):
    handler = modhandler_system.handler
    with patch.object(PedalboardSync, "configure_remote", return_value=SyncResult(status="error", message="Clone failed")):
        handler.init_pedalboards_remote("https://example.com/pb.git")
    assert handler.notification == "Clone failed"


def test_init_pedalboards_remote_sets_notification_on_remote_conflict(modhandler_system: SystemFixture):
    handler = modhandler_system.handler
    msg = "Remote mismatch: local commits not on origin. Resolve via SSH then sync."
    with patch.object(PedalboardSync, "configure_remote", return_value=SyncResult(status="remote_conflict", message=msg)):
        handler.init_pedalboards_remote("https://example.com/pb.git")
    assert handler.notification == msg


# ---------------------------------------------------------------------------
# system_menu_sync_pedalboards — re-clone when .git disappears mid-session
# ---------------------------------------------------------------------------


def test_sync_reclones_when_git_dir_deleted(modhandler_system: SystemFixture):
    """If the user deletes the pedalboards dir mid-session, manual sync re-clones it."""
    handler = modhandler_system.handler
    handler.pedalboards_remote = "https://example.com/pb.git"
    # .git does not exist (dir was deleted), so system_menu_sync_pedalboards
    # should call configure_remote → _clone rather than apply
    with patch.object(PedalboardSync, "configure_remote",
                      return_value=SyncResult(status="cloned", message="Pedalboards cloned — restart sound engine to load")) as mock_configure:
        result = handler.system_menu_sync_pedalboards()
    mock_configure.assert_called_once_with("https://example.com/pb.git")
    assert result.status == "cloned"


def test_sync_falls_back_to_apply_when_no_remote_configured(modhandler_system: SystemFixture):
    """Without a configured remote, manual sync just runs apply (no clone attempt)."""
    handler = modhandler_system.handler
    assert handler.pedalboards_remote is None
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="Already up to date", stderr="")
    with patch("subprocess.run", return_value=completed):
        result = handler.system_menu_sync_pedalboards()
    assert result.status == "up_to_date"


def test_sync_reclones_empty_dir(modhandler_system: SystemFixture, tmp_path):
    """If the dir exists but is empty (user wiped contents), clone still succeeds."""
    handler = modhandler_system.handler
    handler.pedalboards_remote = "https://example.com/pb.git"
    # Override data_dir so the empty tmp_path/.pedalboards dir is used
    handler.data_dir = str(tmp_path)
    pedalboards_dir = tmp_path / ".pedalboards"
    pedalboards_dir.mkdir()
    # dir exists, is empty, no .git → should attempt clone
    with patch("subprocess.run", return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")):
        result = handler.system_menu_sync_pedalboards()
    assert result.status == "cloned"
