# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Concrete parametric EQ panel for the fil4 / x42-eq plugin."""

from __future__ import annotations

from plugins.eq.parametric import ParametricEqPanel
from plugins.fil4.band_spec import BAND_SPECS


class Fil4Panel(ParametricEqPanel):
    """Full-screen panel for editing an x42-eq (fil4) instance."""

    _show_axis_labels: bool = False

    def build_band_specs(self):
        return BAND_SPECS
