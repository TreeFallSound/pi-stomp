"""Unit tests for blend/parameter_setter.py — ParameterSetter."""

import logging

import pytest
from unittest.mock import MagicMock

from blend.parameter_setter import ParameterSetter


@pytest.fixture
def bridge():
    mock = MagicMock()
    mock.send_parameter.return_value = True
    return mock


@pytest.fixture
def setter(bridge):
    return ParameterSetter(bridge)


def test_first_send_always_goes_through(bridge, setter):
    result = setter.send_parameter("Fx", "Vol", 0.5)
    assert result is True
    bridge.send_parameter.assert_called_once_with("Fx", "Vol", 0.5)


def test_same_value_within_tolerance_skipped(bridge, setter):
    setter.send_parameter("Fx", "Vol", 0.5)
    bridge.reset_mock()
    result = setter.send_parameter("Fx", "Vol", 0.5 + 1e-6)
    assert result is False
    bridge.send_parameter.assert_not_called()


def test_value_outside_tolerance_sends(bridge, setter):
    setter.send_parameter("Fx", "Vol", 0.5)
    bridge.reset_mock()
    result = setter.send_parameter("Fx", "Vol", 0.5 + 0.01)
    assert result is True
    bridge.send_parameter.assert_called_once()


def test_reset_tracking_allows_resend(bridge, setter):
    setter.send_parameter("Fx", "Vol", 0.5)
    setter.reset_tracking()
    bridge.reset_mock()
    result = setter.send_parameter("Fx", "Vol", 0.5)
    assert result is True
    bridge.send_parameter.assert_called_once()


def test_bridge_backpressure_returns_false(bridge, setter, caplog):
    bridge.send_parameter.return_value = False
    with caplog.at_level(logging.WARNING):
        result = setter.send_parameter("Fx", "Vol", 0.5)
    assert result is False
    assert "Dropped" in caplog.text
