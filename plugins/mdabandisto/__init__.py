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

"""Registration for the mod-mda-Bandisto plugin."""

from __future__ import annotations

from common.parameter import Symbol
from modalapi.plugin_customization import PinnedParam
from plugins.customization import PluginCustomization, register
from uilib.misc import fmt_hz

MDA_BANDISTO_URI = "http://moddevices.com/plugins/mda/Bandisto"

register(
    MDA_BANDISTO_URI,
    customization=PluginCustomization(
        display_name="MDA Bandisto",
        pinned_params=(
            PinnedParam(Symbol("l_m"), "L↔M", display_fn=fmt_hz),
            PinnedParam(Symbol("m_h"), "M↔H", display_fn=fmt_hz),
            PinnedParam(Symbol("l_dist"), "L Dist"),
            PinnedParam(Symbol("m_dist"), "M Dist"),
            PinnedParam(Symbol("h_dist"), "H Dist"),
            PinnedParam(Symbol("l_out"), "L Out"),
            PinnedParam(Symbol("m_out"), "M Out"),
            PinnedParam(Symbol("h_out"), "H Out"),
        ),
    ),
)
