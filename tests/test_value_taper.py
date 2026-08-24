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

"""Value <-> normalized-position conversion honoring a parameter's taper.

mod-host maps an incoming MIDI CC onto a plugin port using the port's own taper:
linear ports interpolate arithmetically, logarithmic ports geometrically
(``value = min * (max/min) ** (cc/127)``). pi-stomp must emit the CC that
inverts that map, or a logarithmic port lands on the wrong (too-small) value.
"""

import common.util as util


def test_linear_normalize_matches_renormalize():
    # Linear path is unchanged: normalized*127 == the old renormalize.
    assert util.to_normalized(0.25, 0.0, 1.0, logarithmic=False) == 0.25


def test_linear_round_trip():
    for v in (0.0, 0.3, 0.7, 1.0):
        pos = util.to_normalized(v, 0.0, 1.0, logarithmic=False)
        assert abs(util.from_normalized(pos, 0.0, 1.0, logarithmic=False) - v) < 1e-9


def test_log_round_trip_over_x42_highpass_range():
    # x42-eq highpass: logarithmic, 30..800 Hz.
    for v in (30.0, 100.0, 400.0, 800.0):
        pos = util.to_normalized(v, 30.0, 800.0, logarithmic=True)
        back = util.from_normalized(pos, 30.0, 800.0, logarithmic=True)
        assert abs(back - v) < 1e-6


def test_log_midpoint_is_geometric_not_arithmetic():
    # Position 0.5 on a log 30..800 range is the geometric mean (~155), not 415.
    mid = util.from_normalized(0.5, 30.0, 800.0, logarithmic=True)
    assert abs(mid - (30.0 * 800.0) ** 0.5) < 1e-6
    assert mid < 200.0


def test_log_normalize_differs_from_linear():
    # 400 Hz sits ~79% up the log range but only ~48% up the linear range —
    # the gap that made bar_midi_value emit a too-low CC.
    log_pos = util.to_normalized(400.0, 30.0, 800.0, logarithmic=True)
    lin_pos = util.to_normalized(400.0, 30.0, 800.0, logarithmic=False)
    assert log_pos > 0.75
    assert lin_pos < 0.5
