"""Unit tests for modalapi.pedalboard_monitor.FileChangeMonitor."""

import os
import time
from pathlib import Path

from modalapi.pedalboard_monitor import FileChangeMonitor


def test_initial_no_change(tmp_path: Path):
    """check_for_change() is False the first time after construction."""
    f = tmp_path / "watched"
    f.write_text("v1")
    monitor = FileChangeMonitor(str(f))
    assert monitor.check_for_change() is False


def test_detects_external_modification(tmp_path: Path):
    f = tmp_path / "watched"
    f.write_text("v1")
    monitor = FileChangeMonitor(str(f))
    time.sleep(0.01)  # ensure mtime delta
    f.write_text("v2")
    assert monitor.check_for_change() is True


def test_detects_only_once_per_modification(tmp_path: Path):
    f = tmp_path / "watched"
    f.write_text("v1")
    monitor = FileChangeMonitor(str(f))
    time.sleep(0.01)
    f.write_text("v2")
    assert monitor.check_for_change() is True
    # Baseline updated; no further change until next modification.
    assert monitor.check_for_change() is False


def test_reset_makes_self_write_invisible(tmp_path: Path):
    """The malformed-last.json recovery path: we write last.json ourselves,
    then the next poll would normally see our own write as a change. After
    reset() the monitor baselines against our write and the next poll is
    a no-op."""
    f = tmp_path / "watched"
    f.write_text("v1")
    monitor = FileChangeMonitor(str(f))
    time.sleep(0.01)

    # Simulate: caller writes a new value.
    f.write_text("v2")
    # Caller calls reset() to re-baseline against its own write.
    monitor.reset()
    # Next poll must NOT report a change.
    assert monitor.check_for_change() is False

    # A subsequent external modification is still detected.
    time.sleep(0.01)
    f.write_text("v3")
    assert monitor.check_for_change() is True


def test_reset_handles_missing_file_then_present(tmp_path: Path):
    """If the file is created after construction, reset() picks it up."""
    f = tmp_path / "watched"
    monitor = FileChangeMonitor(str(f))
    assert f.exists() is False

    f.write_text("v1")
    # Without reset, this would be reported as a change.
    monitor.reset()
    assert monitor.check_for_change() is False


def test_reset_uses_current_mtime(tmp_path: Path):
    """reset() captures the file's actual mtime, not the construction-time one."""
    f = tmp_path / "watched"
    f.write_text("v1")
    monitor = FileChangeMonitor(str(f))
    time.sleep(0.01)
    f.write_text("v2")
    monitor.reset()
    # Confirm baseline now matches file mtime, not the older construction one.
    assert monitor._last_timestamp == os.path.getmtime(str(f))
