"""Unit tests for blend/manager.py — BlendMode config parsing."""

from typing import cast
import pytest
from unittest.mock import MagicMock, patch

from blend.manager import BlendMode
from blend.types import BlendSnapshotConfig, ParamData
from modalapi.parameter import Type as ParameterType
from tests.conftest import FakeWebSocketBridge


def _make_blend_mode(config: BlendSnapshotConfig) -> BlendMode:
    handler = MagicMock()
    handler.current.pedalboard.bundle = "/fake/bundle"
    return BlendMode(handler, config)


def _make_param_data(val_a: float, val_b: float) -> ParamData:
    return ParamData(
        val_a=val_a,
        val_b=val_b,
        prev_val=None,
        next_val=None,
        segment_range=1.0,
        param_type=ParameterType.DEFAULT,
    )


# ---------------------------------------------------------------------------
# _normalize_stops_config
# ---------------------------------------------------------------------------


def test_normalize_stops_list_two_items():
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": []})
    result = bm._normalize_stops_config(["A", "B"])
    assert list(result.keys()) == ["0.000000", "1.000000"]
    assert result["0.000000"] == "A"
    assert result["1.000000"] == "B"


def test_normalize_stops_list_three_evenly_spaced():
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": []})
    result = bm._normalize_stops_config(["A", "B", "C"])
    positions = [float(k) for k in result.keys()]
    assert abs(positions[0] - 0.0) < 1e-9
    assert abs(positions[1] - 0.5) < 1e-9
    assert abs(positions[2] - 1.0) < 1e-9
    assert list(result.values()) == ["A", "B", "C"]


def test_normalize_stops_dict_passthrough():
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": {}})
    stops_dict: dict[str, int | str] = {"0.0": "A", "1.0": "B"}
    result = bm._normalize_stops_config(stops_dict)
    assert result is stops_dict


def test_normalize_stops_list_too_short_raises():
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": []})
    with pytest.raises(ValueError, match="at least 2"):
        bm._normalize_stops_config(["only_one"])


# ---------------------------------------------------------------------------
# _validate_config
# ---------------------------------------------------------------------------


def test_validate_config_invalid_interpolation_raises():
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": [], "interpolation": "bogus"})
    with pytest.raises(ValueError, match="Invalid interpolation"):
        bm._validate_config()


def test_validate_config_missing_interpolation_defaults_to_linear():
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": []})
    func = bm._validate_config()
    pd = _make_param_data(0.0, 1.0)
    assert abs(func(0.5, pd) - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# _create_stops — validation errors
# ---------------------------------------------------------------------------

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


def test_create_stops_position_out_of_range_raises(patched_snapshot_manager):
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": {"1.5": "A", "2.0": "B"}})
    with pytest.raises(ValueError, match="out of range"):
        bm._create_stops()


def test_create_stops_non_strictly_increasing_raises(patched_snapshot_manager):
    # "0.5" and "0.50" are different string keys that both parse to position 0.5
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": {"0.5": "A", "0.50": "B"}})
    with pytest.raises(ValueError, match="strictly increasing"):
        bm._create_stops()


def test_create_stops_positions_too_close_for_midi_resolution_raises(patched_snapshot_manager):
    # int(0.001 * 127) == int(0.002 * 127) == 0
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": {"0.001": "A", "0.002": "B"}})
    with pytest.raises(ValueError, match="too close"):
        bm._create_stops()


def test_create_stops_truncates_to_four(patched_snapshot_manager):
    # List of 5 → evenly spaced 0.0, 0.25, 0.5, 0.75, 1.0 → truncated to 4
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": ["A", "B", "C", "D", "E"]})
    stops = bm._create_stops()
    assert len(stops) == 4


def test_create_stops_invalid_position_key_raises(patched_snapshot_manager):
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": {"not_a_float": "A", "1.0": "B"}})
    with pytest.raises(ValueError, match="stringified float"):
        bm._create_stops()


# ---------------------------------------------------------------------------
# _normalize_stops_config — invalid type
# ---------------------------------------------------------------------------


def test_normalize_stops_invalid_type_raises():
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": []})
    with pytest.raises(ValueError, match="dict or list"):
        bm._normalize_stops_config(42)  # pyright: ignore[reportArgumentType]


# ---------------------------------------------------------------------------
# _get_parameter_type
# ---------------------------------------------------------------------------


def test_get_parameter_type_returns_param_type_when_found():
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": []})
    mock_param = MagicMock()
    mock_param.type = ParameterType.TOGGLED
    mock_plugin = MagicMock()
    mock_plugin.instance_id = "/Fx"
    mock_plugin.parameters = {"Switch": mock_param}

    assert bm.handler.current
    bm.handler.current.pedalboard.plugins = [mock_plugin]
    assert bm._get_parameter_type("/Fx", "Switch") == ParameterType.TOGGLED


def test_get_parameter_type_returns_default_when_not_found():
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": []})

    assert bm.handler.current
    bm.handler.current.pedalboard.plugins = []
    assert bm._get_parameter_type("/Unknown", "Vol") == ParameterType.DEFAULT


# ---------------------------------------------------------------------------
# activate / deactivate guards
# ---------------------------------------------------------------------------


def test_activate_without_prepare_raises():
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": []})
    with pytest.raises(RuntimeError, match="not prepared"):
        bm.activate()


def test_activate_sync_failure_detaches_and_reraises():
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": []})
    mock_ic = MagicMock()
    mock_ic.sync_current_position.side_effect = RuntimeError("bridge down")
    bm.input_controller = mock_ic
    bm.parameter_setter = MagicMock()

    with pytest.raises(RuntimeError, match="bridge down"):
        bm.activate()

    mock_ic.detach_from_input.assert_called_once()


def test_deactivate_clears_pending_ws_messages():
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": []})
    bm.input_controller = MagicMock()
    bm.parameter_setter = MagicMock()

    test_ws = cast(FakeWebSocketBridge, bm.handler.ws_bridge)
    test_ws.clear_queue.return_value = 3  # pyright: ignore[reportAttributeAccessIssue]
    bm.deactivate()
    test_ws.clear_queue.assert_called_once()  # pyright: ignore[reportAttributeAccessIssue]


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------


def test_cleanup_resets_state_and_detaches():
    bm = _make_blend_mode({"name": "T", "input_id": 1, "stops": []})
    mock_ic = MagicMock()
    mock_setter = MagicMock()
    bm.input_controller = mock_ic
    bm.parameter_setter = mock_setter
    bm.stops = [MagicMock()]
    bm.segment_diff_maps = [{}]
    test_ws = cast(FakeWebSocketBridge, bm.handler.ws_bridge)
    test_ws.clear_queue.return_value = 0  # pyright: ignore[reportAttributeAccessIssue]

    bm.cleanup()

    mock_ic.detach_from_input.assert_called_once()
    mock_setter.reset_tracking.assert_called_once()
    assert bm.input_controller is None
    assert bm.parameter_setter is None
    assert bm.stops == []
    assert bm.segment_diff_maps == []


