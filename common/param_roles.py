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

"""Parameter role classification: a per-symbol tag supplementing the LV2
port's ground truth (name/range/type) with which symbol a tweak encoder
should resolve off the current selection. Plugin customizations declare a
port's role (`PluginCustomization.param_roles`); GENERIC is the fallback.

The role drives ``Selectable.symbol_for(role)`` — e.g. an EQ band selection
returns a different symbol per role (gain/freq/Q), a compressor arc returns
the same symbol regardless. Step math is unified through ``ParameterSteps``
(``common/parameter_steps.py``); roles no longer carry their own step sizes.
"""

from enum import auto, Enum


class ParamRole(Enum):
    GENERIC = auto()        # fallback: resolve the selection's primary symbol
    GAIN_DB = auto()         # gain symbol of a compound selection
    FREQUENCY_HZ = auto()    # frequency symbol of a compound selection
    Q_FACTOR = auto()        # Q symbol of a compound selection
    PAN = auto()             # pan symbol of a mixer channel selection