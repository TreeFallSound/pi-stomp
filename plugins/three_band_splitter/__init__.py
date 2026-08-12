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

"""Registration for the DISTRHO 3 Band Splitter plugin."""

from __future__ import annotations

from common.parameter import Symbol
from modalapi.plugin_customization import PinnedParam
from plugins.customization import PluginCustomization, register
from uilib.misc import fmt_hz

THREE_BAND_SPLITTER_URI = "http://distrho.sf.net/plugins/3BandSplitter"

register(
    THREE_BAND_SPLITTER_URI,
    customization=PluginCustomization(
        display_name="3 Band Splitter",
        pinned_params=(
            PinnedParam(Symbol("low"), "Low"),
            PinnedParam(Symbol("mid"), "Mid"),
            PinnedParam(Symbol("high"), "High"),
            PinnedParam(Symbol("master"), "Master"),
            PinnedParam(Symbol("low_mid"), "L↔M", display_fn=fmt_hz),
            PinnedParam(Symbol("mid_high"), "M↔H", display_fn=fmt_hz),
        ),
    ),
)
