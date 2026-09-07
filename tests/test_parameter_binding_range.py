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

"""A MIDI-CC binding carries a physical-control sub-range (mod-ui's "Advanced" addressing).
The plugin keeps its declared range; the sub-range controls physical MIDI conversion
and step grids only.
"""

from common.parameter import MidiCC, Parameter, PortInfo
from modalapi.pedalboard import Pedalboard


def _port(minimum: float = 0.0, maximum: float = 1.0) -> PortInfo:
    return PortInfo(shortName="gain", symbol="gain", ranges={"minimum": minimum, "maximum": maximum})


def test_binding_range_sets_physical_extents():
    p = Parameter(_port(0.0, 1.0), 0.25, binding="0:70", binding_range=(0.0, 0.5))
    assert p.minimum == 0.0
    assert p.maximum == 0.5


def test_unmapped_parameter_physical_extents_match_declared():
    p = Parameter(_port(0.0, 1.0), 0.25, binding="0:70")
    assert p.minimum == 0.0
    assert p.maximum == 1.0


def test_set_binding_range_updates_physical_extents():
    p = Parameter(_port(0.0, 1.0), 0.25, binding=None)
    p.set_binding_range((0.2, 0.6))
    assert (p.minimum, p.maximum) == (0.2, 0.6)


def test_set_binding_range_updates_physical_extents_to_new_mapping():
    """A re-address can replace a custom MIDI sub-range with the full range."""
    p = Parameter(_port(0.0, 1.0), 0.25, binding="0:70", binding_range=(0.0, 0.5))
    p.set_binding_range((0.0, 1.0))
    assert (p.minimum, p.maximum) == (0.0, 1.0)


def test_set_binding_range_preserves_parameter_identity():
    """The same Parameter object keeps all controller and UI references valid."""
    p = Parameter(_port(0.0, 1.0), 0.25, binding=None)
    before = id(p)
    p.set_binding_range((0.2, 0.6))
    assert id(p) == before


def test_clear_binding_range_restores_declared_physical_extents():
    p = Parameter(_port(30.0, 800.0), 100.0, binding="0:70", binding_range=(100.0, 400.0))
    assert (p.minimum, p.maximum) == (100.0, 400.0)
    p.clear_binding_range()
    assert (p.minimum, p.maximum) == (30.0, 800.0)


def test_binding_range_change_preserves_parameter_value():
    """Changing MIDI coverage must not change the MOD-owned port value."""
    p = Parameter(_port(0.0, 1.0), 0.9, binding="0:70", binding_range=(0.0, 1.0))
    notifications = []
    p.subscribe(lambda param: notifications.append(param.value))

    p.set_binding_range((0.0, 0.5))
    assert p.value == 0.9
    assert p._confirmed == 0.9
    assert notifications == []

    p.clear_binding_range()
    assert (p.minimum, p.maximum) == (0.0, 1.0)
    assert p.value == 0.9
    assert p._confirmed == 0.9
    assert notifications == []


def test_set_binding_range_is_idempotent():
    """A connect dump can repeat the same physical extents without a value event."""
    p = Parameter(_port(0.0, 1.0), 0.5, binding="0:70", binding_range=(0.0, 0.5))
    notifications = []
    p.subscribe(lambda param: notifications.append(param.value))
    p.set_binding_range((0.0, 0.5))
    assert len(notifications) == 0


def test_clear_binding_range_is_idempotent():
    """A repeated unmap does not create a value event."""
    p = Parameter(_port(30.0, 800.0), 400.0, binding="0:70", binding_range=(100.0, 400.0))
    notifications = []
    p.subscribe(lambda param: notifications.append(param.value))
    p.clear_binding_range()
    assert len(notifications) == 0
    p.clear_binding_range()
    assert len(notifications) == 0


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
