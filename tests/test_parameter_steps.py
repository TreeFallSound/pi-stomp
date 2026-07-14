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

"""The step grid shared by the nav encoder (Parameterdialog) and v3 tweak
encoders (EncoderController), so one detent moves a parameter identically
whichever control is turned."""

import pytest

from common.parameter import Parameter, Type
from common.parameter_steps import CONTINUOUS_STEPS, ParameterSteps, resolution
from pistomp.encoder_controller import EncoderController


def _param(minimum: float, maximum: float, value: float, type: Type = Type.DEFAULT) -> Parameter:
    p = Parameter(
        {"shortName": "test", "symbol": "test", "ranges": {"minimum": minimum, "maximum": maximum}},
        value,
        binding=None,
    )
    p.type = type
    return p


# ── resolution ───────────────────────────────────────────────────────────


def test_unbound_encoder_gets_full_midi_sweep():
    """A free-running CC must still reach all 128 MIDI values."""
    assert resolution(None) == CONTINUOUS_STEPS


def test_continuous_parameter_gets_128_steps():
    assert resolution(_param(0.0, 1.0, 0.5)) == CONTINUOUS_STEPS


def test_integer_parameter_gets_one_step_per_unit():
    assert resolution(_param(0, 10, 5, Type.INTEGER)) == 11


def test_toggled_parameter_gets_two_steps():
    assert resolution(_param(0, 1, 0, Type.TOGGLED)) == 2


def test_enumeration_parameter_gets_one_step_per_entry():
    p = _param(0, 2, 0, Type.ENUMERATION)
    p.enum_values = [{"label": "a", "value": 0}, {"label": "b", "value": 1}, {"label": "c", "value": 2}]
    assert resolution(p) == 3


# ── grid ─────────────────────────────────────────────────────────────────


def test_linear_grid_spans_the_range():
    steps = ParameterSteps(0.0, 10.0, taper=1.0, num_steps=11)
    assert steps.values[0] == pytest.approx(0.0)
    assert steps.values[-1] == pytest.approx(10.0)
    assert steps.values[5] == pytest.approx(5.0)


def test_tapered_grid_is_denser_at_the_bottom():
    """A log parameter's detents move less near the minimum."""
    steps = ParameterSteps(0.0, 100.0, taper=2.0, num_steps=11)
    low = steps.values[1] - steps.values[0]
    high = steps.values[-1] - steps.values[-2]
    assert low < high


def test_degenerate_grid_collapses_to_minimum():
    steps = ParameterSteps(5.0, 5.0, taper=1.0, num_steps=1)
    assert steps.values == [5.0]
    assert steps.value == 5.0
    assert steps.normalized == 0.0


def test_move_clamps_at_both_ends():
    steps = ParameterSteps(0.0, 1.0, taper=1.0, num_steps=5)
    assert steps.move(-10) == pytest.approx(0.0)
    assert steps.move(100) == pytest.approx(1.0)
    assert steps.index == 4


def test_normalized_tracks_position():
    steps = ParameterSteps(0.0, 1.0, taper=1.0, num_steps=5)
    steps.move(2)
    assert steps.normalized == pytest.approx(0.5)


@pytest.mark.parametrize(
    "value, expected_index",
    [
        (-1.0, 0),  # below the range
        (0.0, 0),
        (0.24, 1),  # snaps to nearest, not floor
        (0.26, 1),
        (1.0, 4),
        (99.0, 4),  # above the range
    ],
)
def test_set_value_snaps_to_nearest_step(value, expected_index):
    steps = ParameterSteps(0.0, 1.0, taper=1.0, num_steps=5)
    steps.set_value(value)
    assert steps.index == expected_index


def test_for_parameter_seeds_cursor_from_current_value():
    steps = ParameterSteps.for_parameter(_param(0.0, 1.0, 0.5))
    assert steps.value == pytest.approx(0.5, abs=0.01)


# ── nav / tweak equivalence ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "param",
    [
        _param(0.0, 1.0, 0.5),
        _param(-20.0, 20.0, 0.0),
        _param(0, 10, 5, Type.INTEGER),
        _param(0, 1, 0, Type.TOGGLED),
        _param(20.0, 20000.0, 440.0, Type.LOGARITHMIC),
    ],
    ids=["unit", "bipolar", "integer", "toggled", "logarithmic"],
)
def test_tweak_encoder_and_dialog_share_the_same_grid(param):
    """A MIDI-bound tweak encoder must quantize onto exactly the grid the nav
    encoder steps through — guards against reintroducing a midi_CC short-circuit
    in the resolution rule."""
    enc = EncoderController(d_pin=None, clk_pin=None, midi_CC=70, midi_channel=0)
    enc.bind_to_parameter(param)

    dialog_grid = ParameterSteps.for_parameter(param)

    assert enc.num_steps == dialog_grid.num_steps
    assert enc.step_values == pytest.approx(dialog_grid.values)
    assert enc.current_step == dialog_grid.index


def test_one_detent_moves_tweak_and_nav_identically():
    """The multiplier scales step count for both, so 2 detents at 3x = 6 steps."""
    param = _param(0.0, 1.0, 0.0, Type.LOGARITHMIC)

    enc = EncoderController(d_pin=None, clk_pin=None, midi_CC=70, midi_channel=0)
    enc.bind_to_parameter(param)
    enc_value = enc._move_steps(int(round(2 * 3.0)))

    nav_grid = ParameterSteps.for_parameter(_param(0.0, 1.0, 0.0, Type.LOGARITHMIC))
    nav_value = nav_grid.move(int(round(1 * 2 * 3.0)))

    assert enc_value == pytest.approx(nav_value)
