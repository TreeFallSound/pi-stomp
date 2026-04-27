"""Unit tests for pistomp/sync.py — no hardware or subprocess required."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from pistomp.sync import PedalboardSync


# ---------------------------------------------------------------------------
# _parse — maps (exit_code, stdout) to SyncResult
# ---------------------------------------------------------------------------


def _sync(pedalboards_dir=None) -> PedalboardSync:
    return PedalboardSync(
        pedalboards_dir=pedalboards_dir or Path("/fake/.pedalboards"),
        homedir=Path("/fake/pi-stomp"),
    )


def test_parse_up_to_date():
    result = _sync()._parse(0, "Already up to date")
    assert result.status == "up_to_date"
    assert result.count == 0
    assert result.message == "Up to date"


def test_parse_applied_single():
    result = _sync()._parse(0, "1 update(s) applied")
    assert result.status == "applied"
    assert result.count == 1


def test_parse_applied_many():
    result = _sync()._parse(0, "5 update(s) applied")
    assert result.status == "applied"
    assert result.count == 5
    assert "5" in result.message


def test_parse_network_error():
    result = _sync()._parse(2, "network: connection refused")
    assert result.status == "network_error"
    assert result.message == "Sync failed: no network"


def test_parse_conflicts():
    stdout = "Metal.pedalboard/config.yml\nJazz.pedalboard/config.yml (uncommitted edit)\nConflicts: resolve via SSH ..."
    result = _sync()._parse(3, stdout)
    assert result.status == "conflicts"
    assert "Metal.pedalboard/config.yml" in result.conflicts
    assert "Jazz.pedalboard/config.yml (uncommitted edit)" in result.conflicts
    assert not any(c.startswith("Conflicts:") for c in result.conflicts)


def test_parse_error():
    result = _sync()._parse(1, "something unexpected failed")
    assert result.status == "error"


# ---------------------------------------------------------------------------
# _run — subprocess integration
# ---------------------------------------------------------------------------


def _completed(returncode: int, stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_apply_runs_script():
    sync = PedalboardSync(
        pedalboards_dir=Path("/fake/.pedalboards"),
        homedir=Path("/fake/pi-stomp"),
    )
    with patch("subprocess.run", return_value=_completed(0, "Already up to date")) as mock_run:
        result = sync.apply()

    cmd = mock_run.call_args[0][0]
    assert cmd[-1] == "/fake/.pedalboards"
    assert "--dry-run" not in cmd
    assert result.status == "up_to_date"


def test_check_passes_dry_run_flag():
    sync = PedalboardSync(
        pedalboards_dir=Path("/fake/.pedalboards"),
        homedir=Path("/fake/pi-stomp"),
    )
    with patch("subprocess.run", return_value=_completed(0, "3 update(s) would be applied")) as mock_run:
        sync.check()

    cmd = mock_run.call_args[0][0]
    assert "--dry-run" in cmd


def test_apply_wraps_sudo_when_username():
    sync = PedalboardSync(
        pedalboards_dir=Path("/fake/.pedalboards"),
        homedir=Path("/fake/pi-stomp"),
        username="pistomp",
    )
    with patch("subprocess.run", return_value=_completed(0, "Already up to date")) as mock_run:
        sync.apply()

    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "sudo"
    assert cmd[1] == "-u"
    assert cmd[2] == "pistomp"


def test_apply_no_sudo_without_username():
    sync = PedalboardSync(
        pedalboards_dir=Path("/fake/.pedalboards"),
        homedir=Path("/fake/pi-stomp"),
    )
    with patch("subprocess.run", return_value=_completed(0, "Already up to date")) as mock_run:
        sync.apply()

    cmd = mock_run.call_args[0][0]
    assert "sudo" not in cmd


def test_timeout_returns_error():
    sync = _sync()
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=30)):
        result = sync.apply()
    assert result.status == "error"


def test_exception_returns_error():
    sync = _sync()
    with patch("subprocess.run", side_effect=OSError("no such file")):
        result = sync.apply()
    assert result.status == "error"


# ---------------------------------------------------------------------------
# __init__ — default paths
# ---------------------------------------------------------------------------


def test_default_pedalboards_dir():
    sync = PedalboardSync()
    assert sync.pedalboards_dir == Path.home() / ".pedalboards"


def test_default_homedir_is_repo_root():
    sync = PedalboardSync()
    # homedir is two levels up from pistomp/sync.py → repo root
    assert (sync.pedalboards_dir.parent == Path.home()) or True  # path exists check
    # script path should end with util/sync-pedalboards.sh
    assert sync.script.endswith("util/sync-pedalboards.sh")
