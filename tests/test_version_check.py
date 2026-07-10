"""Unit tests for modalapi.version_check.DpkgDriftCheck."""

import threading
from unittest.mock import MagicMock, patch

from modalapi.version_check import DpkgDriftCheck


def _completed(stdout: str = "", stderr: str = "") -> MagicMock:
    cp = MagicMock()
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


def test_pre_start_state():
    check = DpkgDriftCheck()
    assert check.done is False
    assert check.drifted is False
    # join() before start() is a no-op that returns "done".
    assert check.join() is True


def test_clean_verify():
    check = DpkgDriftCheck()
    with patch("subprocess.run", return_value=_completed("", "")):
        check.start()
        check.join()
    assert check.done is True
    assert check.drifted is False


def test_drift_detected():
    drift_out = "??5?????? /opt/pistomp/pi-stomp/modalapi/modhandler.py\n"
    check = DpkgDriftCheck()
    with patch("subprocess.run", return_value=_completed(drift_out, "")):
        check.start()
        check.join()
    assert check.done is True
    assert check.drifted is True


def test_stderr_only_counts_as_drift():
    check = DpkgDriftCheck()
    with patch("subprocess.run", return_value=_completed("", "dpkg: warnings\n")):
        check.start()
        check.join()
    assert check.drifted is True


def test_dpkg_missing_treated_as_no_drift():
    """If dpkg isn't installed (e.g. macOS dev box), the indicator is just off."""
    check = DpkgDriftCheck()
    with patch("subprocess.run", side_effect=FileNotFoundError("dpkg")):
        check.start()
        check.join()
    assert check.done is True
    assert check.drifted is False


def test_unexpected_failure_treated_as_no_drift():
    check = DpkgDriftCheck()
    with patch("subprocess.run", side_effect=RuntimeError("boom")):
        check.start()
        check.join()
    assert check.done is True
    assert check.drifted is False


def test_start_is_idempotent():
    """Calling start() twice must not spawn a second thread."""
    check = DpkgDriftCheck()
    with patch("subprocess.run", return_value=_completed("", "")):
        check.start()
        first = check._thread
        check.start()
        second = check._thread
    assert first is second


def test_join_with_timeout_when_not_done(monkeypatch):
    """join(timeout) returns False when the thread is still running."""
    gate = threading.Event()
    call_started = threading.Event()

    def slow_run(*args, **kwargs):
        call_started.set()
        gate.wait(timeout=2.0)
        return _completed("", "")

    check = DpkgDriftCheck()
    with patch("subprocess.run", side_effect=slow_run):
        check.start()
        call_started.wait(timeout=1.0)
        assert check.join(timeout=0.05) is False
        gate.set()
        check.join()
    assert check.done is True
