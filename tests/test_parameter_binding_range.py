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

"""A MIDI-CC binding can carry a custom sub-range (mod-ui's "Advanced" addressing).
While that binding holds, the encoder sweeps and the LCD reads the sub-range, not
the plugin's declared LV2 range."""

from common.parameter import MidiCC, Parameter, PortInfo
from common.parameter_steps import ParameterSteps
from modalapi.pedalboard import Pedalboard


def _port(minimum: float = 0.0, maximum: float = 1.0) -> PortInfo:
    return PortInfo(shortName="gain", symbol="gain", ranges={"minimum": minimum, "maximum": maximum})


def test_binding_range_overrides_declared_range():
    p = Parameter(_port(0.0, 1.0), 0.25, binding="0:70", binding_range=(0.0, 0.5))
    assert p.minimum == 0.0
    assert p.maximum == 0.5


def test_no_binding_range_uses_declared_range():
    p = Parameter(_port(0.0, 1.0), 0.25, binding="0:70")
    assert p.minimum == 0.0
    assert p.maximum == 1.0


def test_set_binding_range_live_narrows_sweep():
    p = Parameter(_port(0.0, 1.0), 0.25, binding=None)
    p.set_binding_range((0.2, 0.6))
    assert (p.minimum, p.maximum) == (0.2, 0.6)


def test_set_binding_range_widens_to_full_range():
    """mod-host re-sends the effective range on re-address — a re-map back to the
    full range arrives as the declared extents and overwrites the sub-range."""
    p = Parameter(_port(0.0, 1.0), 0.25, binding="0:70", binding_range=(0.0, 0.5))
    p.set_binding_range((0.0, 1.0))
    assert (p.minimum, p.maximum) == (0.0, 1.0)


def test_set_binding_range_preserves_identity():
    """The range mutates in place — the same Parameter object, so every
    controller/dialog/subscriber holding it stays wired."""
    p = Parameter(_port(0.0, 1.0), 0.25, binding=None)
    before = id(p)
    p.set_binding_range((0.2, 0.6))
    assert id(p) == before


def test_step_grid_sweeps_only_the_sub_range():
    """The encoder grid's endpoints follow the sub-range, so a full spin can no
    longer reach the plugin's declared maximum."""
    p = Parameter(_port(0.0, 1.0), 0.0, binding="0:70", binding_range=(0.0, 0.5))
    steps = ParameterSteps.for_parameter(p)
    assert steps.values[0] == 0.0
    assert steps.values[-1] == 0.5


# ── Pedalboard._binding_range (the static pedalboard/info midiCC dict) ──────


def test_binding_range_from_midicc_with_custom_ranges():
    cc = MidiCC(channel=0, control=70, hasRanges=True, minimum=0.0, maximum=0.5)
    assert Pedalboard._binding_range(cc) == (0.0, 0.5)


def test_binding_range_none_without_hasranges():
    cc = MidiCC(channel=0, control=70, hasRanges=False, minimum=0.0, maximum=1.0)
    assert Pedalboard._binding_range(cc) is None


def test_binding_range_none_when_unmapped():
    assert Pedalboard._binding_range(None) is None
    assert Pedalboard._binding_range(MidiCC(channel=-1, control=0, hasRanges=True, minimum=0.0, maximum=0.5)) is None


def test_binding_range_none_when_degenerate():
    cc = MidiCC(channel=0, control=70, hasRanges=True, minimum=0.5, maximum=0.5)
    assert Pedalboard._binding_range(cc) is None
