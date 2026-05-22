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


def test_same_value_within_tolerance_skipped(bridge, setter):
    setter.send_parameter("Fx", "Vol", 0.5)
    bridge.reset_mock()
    result = setter.send_parameter("Fx", "Vol", 0.5 + 1e-6)
    assert result is False
    bridge.send_parameter.assert_not_called()


def test_bridge_backpressure_returns_false(bridge, setter, caplog):
    bridge.send_parameter.return_value = False
    with caplog.at_level(logging.WARNING):
        result = setter.send_parameter("Fx", "Vol", 0.5)
    assert result is False
    assert "Dropped" in caplog.text
