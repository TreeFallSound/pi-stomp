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


def test_resolve_by_name_case_insensitive():
    assert SnapshotManager.resolve_snapshot_identifier(_SNAPSHOTS, "clean") == 0


def test_resolve_by_name_not_found_raises():
    with pytest.raises(ValueError):
        SnapshotManager.resolve_snapshot_identifier(_SNAPSHOTS, "Nonexistent")


def test_resolve_by_index_out_of_range_raises():
    with pytest.raises(ValueError):
        SnapshotManager.resolve_snapshot_identifier(_SNAPSHOTS, 99)


def test_parse_snapshot_data_extracts_ports():
    state = SnapshotManager.parse_snapshot_data(_SNAPSHOTS, 0)
    assert state["BigMuff"]["Tone"] == pytest.approx(0.2)
    assert state["BigMuff"]["Level"] == pytest.approx(0.5)


def test_parse_snapshot_data_maps_bypassed_to_bypass_param():
    state = SnapshotManager.parse_snapshot_data(_SNAPSHOTS, 1)
    assert state["BigMuff"][":bypass"] == pytest.approx(1.0)


def test_parse_snapshot_data_uses_canonical_instance_id():
    """Snapshot state keys must be canonical (no leading slash) so they match
    Plugin.instance_id and route cleanly through websocket_bridge.send_parameter."""
    state = SnapshotManager.parse_snapshot_data(_SNAPSHOTS, 0)
    for key in state:
        assert not key.startswith("/"), f"snapshot key {key!r} leaked a leading slash"


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
def test_sync_recreates_snapshot_with_stale_data(mock_get, tmp_path):
    mock_get.return_value = MagicMock(status_code=200)
    stale = {"BigMuff": {"bypassed": False, "ports": {"Tone": 0.5}, "parameters": {}, "preset": ""}}
    data = {**_SNAPSHOTS, "snapshots": list(_SNAPSHOTS["snapshots"]) + [{"name": "Blend", "data": stale}]}
    (tmp_path / "snapshots.json").write_text(json.dumps(data))

    SnapshotManager.sync_blend_snapshots(tmp_path, _BLEND_CONFIGS, "http://localhost/")

    updated = json.loads((tmp_path / "snapshots.json").read_text())
    blend_snap = next(s for s in updated["snapshots"] if s["name"] == "Blend")
    assert blend_snap["data"] == {}
