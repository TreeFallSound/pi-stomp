"""Unit tests for blend/input_controller.py — InputController."""

import logging

import pytest
from unittest.mock import MagicMock

from blend.input_controller import InputController
from blend.interpolation import linear_interpolation
from blend.stop import BlendStop
from blend.types import ParamData
from modalapi.parameter import Type as ParameterType


def _make_stop(position: float) -> BlendStop:
    return BlendStop(position, 0, {})


def _make_param_data(val_a: float, val_b: float) -> ParamData:
    return ParamData(
        val_a=val_a,
        val_b=val_b,
        prev_val=None,
        next_val=None,
        segment_range=1.0,
        param_type=ParameterType.DEFAULT,
    )


def _make_controller(stops, diff_maps=None) -> InputController:
    if diff_maps is None:
        diff_maps = [{} for _ in range(len(stops) - 1)]
    return InputController(linear_interpolation, stops, diff_maps, MagicMock())


# ---------------------------------------------------------------------------
# _find_segment
# ---------------------------------------------------------------------------


@pytest.fixture
def two_stop_controller():
    return _make_controller([_make_stop(0.0), _make_stop(1.0)])


@pytest.fixture
def three_stop_controller():
    return _make_controller([_make_stop(0.0), _make_stop(0.5), _make_stop(1.0)])


def test_find_segment_two_stops_left_half(two_stop_controller):
    assert two_stop_controller._find_segment(0.3) == 0


def test_find_segment_two_stops_right_half(two_stop_controller):
    # Only one segment, so 0.7 still maps to segment 0
    assert two_stop_controller._find_segment(0.7) == 0


def test_find_segment_three_stops_middle(three_stop_controller):
    # 0.6 is in the second segment (0.5 → 1.0)
    assert three_stop_controller._find_segment(0.6) == 1


def test_find_segment_clamps_negative(two_stop_controller):
    assert two_stop_controller._find_segment(-0.1) == 0


def test_find_segment_clamps_above_one(two_stop_controller):
    assert two_stop_controller._find_segment(1.1) == 0


# ---------------------------------------------------------------------------
# handle_value_change
# ---------------------------------------------------------------------------


@pytest.fixture
def interpolating_controller():
    stops = [_make_stop(0.0), _make_stop(1.0)]
    param_data = _make_param_data(0.0, 1.0)
    diff_map = {"/Plugin": {"Param": param_data}}
    mock_setter = MagicMock()
    mock_setter.send_parameter.return_value = True
    ic = InputController(linear_interpolation, stops, [diff_map], mock_setter)
    return ic, mock_setter


def test_handle_value_change_calls_setter_with_interpolated_value(interpolating_controller):
    ic, mock_setter = interpolating_controller
    control = MagicMock()
    ic._get_normalized_position = lambda ctrl: 0.5
    ic.handle_value_change(0, control)
    mock_setter.send_parameter.assert_called_once()
    _, _, value = mock_setter.send_parameter.call_args.args
    assert abs(value - 0.5) < 1e-6


def test_handle_value_change_exception_does_not_propagate(interpolating_controller):
    ic, mock_setter = interpolating_controller
    mock_setter.send_parameter.side_effect = RuntimeError("boom")
    control = MagicMock()
    ic._get_normalized_position = lambda ctrl: 0.5
    # Must not raise
    ic.handle_value_change(0, control)


# ---------------------------------------------------------------------------
# attach_to_input / detach_from_input
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_controller():
    return _make_controller([_make_stop(0.0), _make_stop(1.0)])


def _analog_control(id: int) -> MagicMock:
    ctrl = MagicMock()
    ctrl.id = id
    ctrl.value_change_callback = None
    return ctrl


def test_attach_sets_callback(simple_controller):
    ic = simple_controller
    control = _analog_control(1)
    ic.attach_to_input([control], [], 1)
    cb = control.value_change_callback
    # Bound methods are freshly created on each access, so compare via __func__/__self__
    assert cb.__func__ is InputController.handle_value_change
    assert cb.__self__ is ic
    assert ic.controlled_input is control


def test_detach_clears_callback(simple_controller):
    ic = simple_controller
    control = _analog_control(1)
    ic.attach_to_input([control], [], 1)
    ic.detach_from_input()
    assert control.value_change_callback is None
    assert ic.controlled_input is None


def test_attach_non_encoder_midi_control_raises(simple_controller):
    # A plain MagicMock in the encoders list is not an EncoderMidiControl → should raise
    plain_encoder = MagicMock()
    plain_encoder.id = 1
    with pytest.raises(ValueError, match="EncoderMidiControl"):
        simple_controller.attach_to_input([], [plain_encoder], 1)


def test_attach_missing_input_id_raises(simple_controller):
    control = _analog_control(99)  # wrong id
    with pytest.raises(ValueError, match="not found"):
        simple_controller.attach_to_input([control], [], 1)


# ---------------------------------------------------------------------------
# _get_normalized_position — expression pedal path
# ---------------------------------------------------------------------------


def test_get_normalized_position_expression_pedal():
    ic = _make_controller([_make_stop(0.0), _make_stop(1.0)])
    control = MagicMock(spec=[])  # plain object, not EncoderMidiControl
    control.last_read = 512
    result = ic._get_normalized_position(control)
    assert result == pytest.approx(512 / 1023.0, rel=1e-9)


# ---------------------------------------------------------------------------
# sync_current_position
# ---------------------------------------------------------------------------


def test_sync_current_position_warns_when_no_input_attached(caplog):
    ic = _make_controller([_make_stop(0.0), _make_stop(1.0)])
    with caplog.at_level(logging.WARNING):
        ic.sync_current_position()
    assert "no controlled input" in caplog.text.lower()


def test_sync_current_position_sends_constant_params():
    state = {"/Fx": {"Const": 0.75}}
    stop_a = BlendStop(0.0, 0, state)
    stop_b = BlendStop(1.0, 1, state)  # identical state → nothing in diff map
    mock_setter = MagicMock()
    mock_setter.send_parameter.return_value = True
    ic = InputController(linear_interpolation, [stop_a, stop_b], [{}], mock_setter)

    control = _analog_control(1)
    ic.attach_to_input([control], [], 1)
    ic._get_normalized_position = lambda control: 0.5
    ic.sync_current_position()

    mock_setter.send_parameter.assert_called_once_with("/Fx", "Const", 0.75)


