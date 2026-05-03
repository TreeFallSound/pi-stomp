"""Unit tests for blend/snapshot.py — SnapshotManager."""

import json

import pytest
from unittest.mock import MagicMock, patch

from blend.snapshot import SnapshotManager
from blend.types import BlendSnapshotConfig, SnapshotsJson


_SNAPSHOTS: SnapshotsJson = {
    "current": 0,
    "snapshots": [
        {
            "name": "Clean",
            "data": {
                "BigMuff": {
                    "bypassed": False,
                    "ports": {"Tone": 0.2, "Level": 0.5},
                    "parameters": {},
                    "preset": "",
                }
            },
        },
        {
            "name": "Lead",
            "data": {
                "BigMuff": {
                    "bypassed": True,
                    "ports": {"Tone": 0.8, "Level": 0.9},
                    "parameters": {},
                    "preset": "",
                }
            },
        },
    ],
}


# ---------------------------------------------------------------------------
# read_snapshots_file
# ---------------------------------------------------------------------------


def test_read_snapshots_file_parses_json(tmp_path):
    (tmp_path / "snapshots.json").write_text(json.dumps(_SNAPSHOTS))
    data = SnapshotManager.read_snapshots_file(tmp_path)
    assert data["current"] == 0
    assert len(data["snapshots"]) == 2


def test_read_snapshots_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        SnapshotManager.read_snapshots_file(tmp_path)


def test_read_snapshots_invalid_json_raises_value_error(tmp_path):
    (tmp_path / "snapshots.json").write_text("{not valid json}")
    with pytest.raises(ValueError):
        SnapshotManager.read_snapshots_file(tmp_path)


# ---------------------------------------------------------------------------
# resolve_snapshot_identifier
# ---------------------------------------------------------------------------


def test_resolve_by_index_valid():
    assert SnapshotManager.resolve_snapshot_identifier(_SNAPSHOTS, 1) == 1


def test_resolve_by_index_out_of_range_raises():
    with pytest.raises(ValueError):
        SnapshotManager.resolve_snapshot_identifier(_SNAPSHOTS, 99)


def test_resolve_by_name_exact_match():
    assert SnapshotManager.resolve_snapshot_identifier(_SNAPSHOTS, "Clean") == 0


def test_resolve_by_name_case_insensitive():
    assert SnapshotManager.resolve_snapshot_identifier(_SNAPSHOTS, "clean") == 0


def test_resolve_by_name_not_found_raises():
    with pytest.raises(ValueError):
        SnapshotManager.resolve_snapshot_identifier(_SNAPSHOTS, "Nonexistent")


# ---------------------------------------------------------------------------
# parse_snapshot_data
# ---------------------------------------------------------------------------


def test_parse_snapshot_data_extracts_ports():
    state = SnapshotManager.parse_snapshot_data(_SNAPSHOTS, 0)
    assert "/BigMuff" in state
    assert state["/BigMuff"]["Tone"] == pytest.approx(0.2)
    assert state["/BigMuff"]["Level"] == pytest.approx(0.5)


def test_parse_snapshot_data_maps_bypassed_to_bypass_param():
    # Lead snapshot has bypassed=True → :bypass = 1.0
    state = SnapshotManager.parse_snapshot_data(_SNAPSHOTS, 1)
    assert state["/BigMuff"][":bypass"] == pytest.approx(1.0)


def test_parse_snapshot_data_adds_leading_slash_to_instance_id():
    state = SnapshotManager.parse_snapshot_data(_SNAPSHOTS, 0)
    assert "/BigMuff" in state
    assert "BigMuff" not in state


# ---------------------------------------------------------------------------
# sync_blend_snapshots
# ---------------------------------------------------------------------------


_BLEND_CONFIGS: list[BlendSnapshotConfig] = [{"name": "Blend", "input_id": 1, "stops": ["Clean", "Lead"]}]


@patch("blend.snapshot.req.get")
def test_sync_creates_empty_snapshot_when_none_exists(mock_get, tmp_path):
    mock_get.return_value = MagicMock(status_code=200)
    (tmp_path / "snapshots.json").write_text(json.dumps(_SNAPSHOTS))

    indices = SnapshotManager.sync_blend_snapshots(tmp_path, _BLEND_CONFIGS, "http://localhost/")

    assert "Blend" in indices
    updated = json.loads((tmp_path / "snapshots.json").read_text())
    blend_snap = next(s for s in updated["snapshots"] if s["name"] == "Blend")
    assert blend_snap["data"] == {}


@patch("blend.snapshot.req.get")
def test_sync_skips_if_empty_snapshot_already_exists(mock_get, tmp_path):
    data = {**_SNAPSHOTS, "snapshots": list(_SNAPSHOTS["snapshots"]) + [{"name": "Blend", "data": {}}]}
    (tmp_path / "snapshots.json").write_text(json.dumps(data))
    mtime_before = (tmp_path / "snapshots.json").stat().st_mtime

    SnapshotManager.sync_blend_snapshots(tmp_path, _BLEND_CONFIGS, "http://localhost/")

    assert (tmp_path / "snapshots.json").stat().st_mtime == mtime_before
    mock_get.assert_not_called()


@patch("blend.snapshot.req.get")
def test_sync_recreates_snapshot_with_stale_data(mock_get, tmp_path):
    mock_get.return_value = MagicMock(status_code=200)
    stale = {"BigMuff": {"bypassed": False, "ports": {"Tone": 0.5}, "parameters": {}, "preset": ""}}
    data = {**_SNAPSHOTS, "snapshots": list(_SNAPSHOTS["snapshots"]) + [{"name": "Blend", "data": stale}]}
    (tmp_path / "snapshots.json").write_text(json.dumps(data))

    SnapshotManager.sync_blend_snapshots(tmp_path, _BLEND_CONFIGS, "http://localhost/")

    updated = json.loads((tmp_path / "snapshots.json").read_text())
    blend_snap = next(s for s in updated["snapshots"] if s["name"] == "Blend")
    assert blend_snap["data"] == {}


# ---------------------------------------------------------------------------
# parse_snapshot_data — index out of range
# ---------------------------------------------------------------------------


def test_parse_snapshot_data_index_out_of_range_raises():
    with pytest.raises(IndexError):
        SnapshotManager.parse_snapshot_data(_SNAPSHOTS, 99)


# ---------------------------------------------------------------------------
# sync_blend_snapshots — skip conditions
# ---------------------------------------------------------------------------


@patch("blend.snapshot.req.get")
def test_sync_no_blend_configs_returns_empty(mock_get, tmp_path):
    (tmp_path / "snapshots.json").write_text(json.dumps(_SNAPSHOTS))
    assert SnapshotManager.sync_blend_snapshots(tmp_path, None, "http://localhost/") == {}
    assert SnapshotManager.sync_blend_snapshots(tmp_path, [], "http://localhost/") == {}
    mock_get.assert_not_called()


@patch("blend.snapshot.req.get")
def test_sync_config_missing_name_is_skipped(mock_get, tmp_path):
    (tmp_path / "snapshots.json").write_text(json.dumps(_SNAPSHOTS))
    result = SnapshotManager.sync_blend_snapshots(
        tmp_path, [{"input_id": 1, "stops": ["Clean", "Lead"]}], "http://localhost/"  # pyright: ignore[reportArgumentType]
    )
    assert result == {}
    mock_get.assert_not_called()


@patch("blend.snapshot.req.get")
def test_sync_config_missing_stops_is_skipped(mock_get, tmp_path):
    (tmp_path / "snapshots.json").write_text(json.dumps(_SNAPSHOTS))
    result = SnapshotManager.sync_blend_snapshots(
        tmp_path, [{"name": "Blend", "input_id": 1}], "http://localhost/"  # pyright: ignore[reportArgumentType]
    )
    assert result == {}
    mock_get.assert_not_called()


@patch("blend.snapshot.req.get")
def test_sync_config_one_stop_is_skipped(mock_get, tmp_path):
    (tmp_path / "snapshots.json").write_text(json.dumps(_SNAPSHOTS))
    result = SnapshotManager.sync_blend_snapshots(
        tmp_path, [{"name": "Blend", "input_id": 1, "stops": ["Clean"]}], "http://localhost/"
    )
    assert result == {}
    mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# _notify_mod_ui — error paths
# ---------------------------------------------------------------------------


@patch("blend.snapshot.req.get")
def test_notify_mod_ui_exception_does_not_propagate(mock_get):
    mock_get.side_effect = ConnectionError("unreachable")
    SnapshotManager._notify_mod_ui("http://localhost/")  # must not raise
