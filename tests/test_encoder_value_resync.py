# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Unit tests for EncoderController resync when parameter.value is changed externally.

Scenario: a tweak encoder (VOLUME/GAIN/etc.) and nav encoder both edit the same
parameter via a Parameterdialog.  The nav encoder calls parameter_value_change()
which writes directly to parameter.value; the tweak encoder must pick up that
externally-set value as its new baseline on the next turn, not snap back to the
position it quantised before the nav encoder moved.
"""

import pytest
from unittest.mock import MagicMock

from common.parameter import Parameter
from pistomp.encoder_controller import EncoderController


def _make_parameter(minimum: float, maximum: float, value: float) -> Parameter:
    plugin_info = {
        "shortName": "test",
        "symbol": "test",
        "ranges": {"minimum": minimum, "maximum": maximum},
    }
    return Parameter(plugin_info, value, binding=None)


@pytest.fixture
def enc():
    e = EncoderController(d_pin=None, clk_pin=None, midi_CC=70, midi_channel=0)
    e.sink = MagicMock()
    return e


def test_value_continues_from_nav_change(enc):
    """Tweak encoder must continue from externally-set value, not its old step."""
    param = _make_parameter(0.0, 100.0, 50.0)
    enc.bind_to_parameter(param)

    # Tweak encoder: advance a few detents from 50
    enc.refresh(5)
    value_after_tweak = param.value
    assert value_after_tweak > 50.0

    # Nav encoder (simulated via direct write, as parameter_value_change does)
    param.value = 90.0

    # Tweak encoder: one detent forward — should continue from 90, not from old step
    enc.refresh(1)

    assert param.value > 80.0, (
        f"Value snapped back to {param.value:.2f} instead of continuing near 90; "
        f"tweak position before nav was {value_after_tweak:.2f}"
    )


def test_value_stays_near_nav_change_on_backward_turn(enc):
    """Backward tweak after nav change should decrement from the nav value."""
    param = _make_parameter(0.0, 100.0, 50.0)
    enc.bind_to_parameter(param)

    enc.refresh(5)

    # Nav encoder jumps parameter up
    param.value = 80.0

    # Tweak encoder turns backward — should go slightly below 80, not below old position
    enc.refresh(-1)

    assert param.value > 60.0, f"Value snapped back to {param.value:.2f}; expected near 80 after nav set"


def test_no_resync_needed_without_external_change(enc):
    """Sanity: without external change current_step is already consistent."""
    param = _make_parameter(0.0, 100.0, 50.0)
    enc.bind_to_parameter(param)

    enc.refresh(3)
    v1 = param.value
    enc.refresh(3)
    v2 = param.value

    # Both moves should advance value monotonically
    assert v2 > v1
