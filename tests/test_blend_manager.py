"""Unit tests for blend/manager.py — config validation rules."""

import pytest
from unittest.mock import MagicMock, patch

from blend.manager import BlendMode, _resolve_easing
from blend.types import BlendSnapshotConfig


def _make_blend_mode(config: BlendSnapshotConfig) -> BlendMode:
    handler = MagicMock()
    handler.current.pedalboard.bundle = "/fake/bundle"
    return BlendMode(handler, config)


_FAKE_SNAPSHOTS = {
    "current": 0,
    "snapshots": [{"name": n, "data": {}} for n in ["A", "B", "C", "D", "E"]],
}

_RESOLVE_MAP = {str(n): i for i, n in enumerate(["A", "B", "C", "D", "E"])}


@pytest.fixture
def patched_snapshot_manager():
    with (
        patch("blend.manager.SnapshotManager.read_snapshots_file", return_value=_FAKE_SNAPSHOTS),
        patch(
            "blend.manager.SnapshotManager.resolve_snapshot_identifier",
            side_effect=lambda _data, ident: _RESOLVE_MAP.get(str(ident), 0),
        ),
        patch("blend.manager.SnapshotManager.parse_snapshot_data", return_value={}),
    ):
        yield


def test_resolve_easing_invalid_name_raises():
    cfg: BlendSnapshotConfig = {"name": "T", "input_id": 1, "stops": [], "interpolation": "bogus"}
    with pytest.raises(ValueError, match="Invalid interpolation"):
        _resolve_easing(cfg)


def test_create_stops_position_out_of_range_raises(patched_snapshot_manager):
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": {"1.5": "A", "2.0": "B"}})
    with pytest.raises(ValueError, match="out of range"):
        bm._create_stops()


def test_create_stops_non_strictly_increasing_raises(patched_snapshot_manager):
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": {"0.5": "A", "0.50": "B"}})
    with pytest.raises(ValueError, match="strictly increasing"):
        bm._create_stops()


def test_create_stops_positions_too_close_for_midi_resolution_raises(patched_snapshot_manager):
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": {"0.001": "A", "0.002": "B"}})
    with pytest.raises(ValueError, match="too close"):
        bm._create_stops()


def test_create_stops_truncates_to_four(patched_snapshot_manager):
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": ["A", "B", "C", "D", "E"]})
    stops = bm._create_stops()
    assert len(stops) == 4
