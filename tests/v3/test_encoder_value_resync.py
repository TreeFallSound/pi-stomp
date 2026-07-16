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

"""A bound tweak encoder continues from whatever value the parameter currently
holds, including one written externally (nav dialog, mod-ui echo).

Once there was a shadow accumulator on the encoder that had to be resynced to
the parameter after an external write. There is no shadow anymore: the encoder
reports a delta and the handler integrates it onto a fresh
``ParameterSteps.for_parameter(param)`` seeded at the live value every turn, so
"continue from the current value" is structural, not a resync step.
"""

from common.parameter import Parameter, PortInfo
from pistomp.encoder_controller import EncoderController
from tests.types import SystemFixture


def _make_parameter(minimum: float, maximum: float, value: float) -> Parameter:
    plugin_info: PortInfo = {
        "shortName": "test",
        "symbol": "test",
        "ranges": {"minimum": minimum, "maximum": maximum},
    }
    return Parameter(plugin_info, value, binding=None, instance_id="test_plugin")


def _bound_tweak(v3_system: SystemFixture, param: Parameter) -> EncoderController:
    handler = v3_system.handler
    hw = v3_system.hw
    assert handler.current
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()  # main panel; lcd.handle falls through to _handle_encoder
    enc = next(e for e in hw.encoders if isinstance(e, EncoderController) and e.midi_CC is not None)
    enc.bind_to_parameter(param)
    return enc


def test_value_continues_from_nav_change(v3_system: SystemFixture):
    """Tweak encoder must continue from an externally-set value, not its old step."""
    param = _make_parameter(0.0, 100.0, 50.0)
    enc = _bound_tweak(v3_system, param)

    enc.refresh(5)
    assert param.value > 50.0

    # Nav encoder (simulated via direct write, as parameter_value_change does).
    param.value = 90.0

    # One detent forward — continues from 90, not from the pre-nav position.
    enc.refresh(1)
    assert param.value > 80.0


def test_value_stays_near_nav_change_on_backward_turn(v3_system: SystemFixture):
    """Backward tweak after a nav change decrements from the nav value."""
    param = _make_parameter(0.0, 100.0, 50.0)
    enc = _bound_tweak(v3_system, param)

    enc.refresh(5)
    param.value = 80.0
    enc.refresh(-1)

    assert param.value > 60.0


def test_monotonic_without_external_change(v3_system: SystemFixture):
    """Sanity: successive forward turns advance the value monotonically."""
    param = _make_parameter(0.0, 100.0, 50.0)
    enc = _bound_tweak(v3_system, param)

    enc.refresh(3)
    v1 = param.value
    enc.refresh(3)
    v2 = param.value

    assert v2 > v1
