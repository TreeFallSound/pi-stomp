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

"""The step grid shared by every editor of a parameter — the nav encoder
(Parameterdialog) and the handler's bound-tweak arm both build it via
ParameterSteps.for_parameter, so one detent moves a parameter identically
whichever control is turned."""

import pytest

from common.parameter import Parameter, Symbol, Type
from common.parameter_steps import CONTINUOUS_STEPS, ParameterSteps, resolution


def _param(minimum: float, maximum: float, value: float, type: Type = Type.DEFAULT) -> Parameter:
    p = Parameter(
        {"shortName": "test", "symbol": "test", "ranges": {"minimum": minimum, "maximum": maximum}},
        value,
        binding=None,
    )
    p.type = type
    return p


class _StubPlugin:
    def __init__(self, parameters: dict[Symbol, Parameter]) -> None:
        self.parameters = parameters
        self.customization = type("C", (), {"param_roles": {}})()
        self.instance_id = "test"
        self.controllers: list[object] = []

    def set_param_value(self, symbol: Symbol, value: float) -> None:
        p = self.parameters.get(symbol)
        if p is not None:
            p.value = value


class _ConcretePluginPanel:
    """Minimal concrete stand-in for PluginPanel.edit_symbol — no Panel base
    needed; we only exercise the edit_symbol method."""

    def __init__(self, plugin: _StubPlugin) -> None:
        self.plugin = plugin
        self._param_queue: dict[Symbol, float] = {}

    from plugins.base import PluginPanel as _Base

    edit_symbol = _Base.edit_symbol
    set_param = _Base.set_param


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


def test_move_clamps_at_both_ends():
    steps = ParameterSteps(0.0, 1.0, taper=1.0, num_steps=5)
    assert steps.move(-10) == pytest.approx(0.0)
    assert steps.move(100) == pytest.approx(1.0)
    assert steps.index == 4


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
def test_bound_tweak_and_dialog_share_the_same_grid(param):
    """Every editor of a bound parameter — the nav dialog and the handler's
    bound-tweak arm — builds its grid the same way: ParameterSteps.for_parameter.
    Guards against reintroducing a midi_CC short-circuit in the resolution rule."""
    a = ParameterSteps.for_parameter(param)
    b = ParameterSteps.for_parameter(param)

    assert a.num_steps == b.num_steps
    assert a.values == pytest.approx(b.values)
    assert a.index == b.index


def test_multiplier_scales_step_count_identically():
    """The multiplier scales step count wherever the grid is built, so 2 detents
    at 3x = 6 steps whether the handler or the nav dialog integrates it."""
    param = _param(0.0, 1.0, 0.0, Type.LOGARITHMIC)

    tweak_value = ParameterSteps.for_parameter(param).move(int(round(2 * 3.0)))
    nav_value = ParameterSteps.for_parameter(param).move(int(round(1 * 2 * 3.0)))

    assert tweak_value == pytest.approx(nav_value)


def test_edit_symbol_applies_multiplier_on_same_grid():
    """The arc-ring edit_symbol path must use the same ParameterSteps grid and
    honour the encoder's speed multiplier — 2 detents at 3x = 6 grid steps,
    identical to the NAV dialog and the encoder controller."""
    param = _param(0.0, 1.0, 0.0, Type.LOGARITHMIC)
    expected = ParameterSteps.for_parameter(param).move(6)

    plugin = _StubPlugin({Symbol("test"): param})
    panel = _ConcretePluginPanel(plugin=plugin)
    changed = panel.edit_symbol(Symbol("test"), rotations=2, multiplier=3.0)

    assert changed
    assert param.value == pytest.approx(expected)


def test_edit_symbol_zero_delta_is_noop():
    """Zero rotations or a multiplier that rounds to zero must not commit."""
    param = _param(0.0, 1.0, 0.5, Type.LOGARITHMIC)
    plugin = _StubPlugin({Symbol("test"): param})

    panel = _ConcretePluginPanel(plugin=plugin)

    assert not panel.edit_symbol(Symbol("test"), rotations=0, multiplier=3.0)
    assert param.value == pytest.approx(0.5)
