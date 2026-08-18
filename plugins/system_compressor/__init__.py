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

"""System Compressor: pinned arc rings (mode/release/volume).

A full compressor panel (graph + GR meter) doesn't make sense here because
this plugin has no threshold, ratio, or knee ports — it's a streamlined
end-of-chain compressor with just mode/release/volume.
"""

from __future__ import annotations

from common.parameter import Symbol
from modalapi.plugin_customization import PinnedParam
from plugins.customization import PluginCustomization, register

SYSTEM_COMPRESSOR_URI = "http://moddevices.com/plugins/mod-devel/System-Compressor"

_MODES = {1: "Light", 2: "Mild", 3: "Heavy"}


def _fmt_mode(value: float) -> tuple[str, str]:
    return _MODES.get(int(value), f"{value:.0f}"), ""


def _fmt_ms(value: float) -> tuple[str, str]:
    return f"{value:.0f}", "ms"


def _fmt_db(value: float) -> tuple[str, str]:
    return f"{value:+.0f}", "dB"


register(
    SYSTEM_COMPRESSOR_URI,
    customization=PluginCustomization(
        display_name="System Compressor",
        pinned_params=(
            PinnedParam(Symbol("COMP_MODE"), "Mode", display_fn=_fmt_mode),
            PinnedParam(Symbol("RELEASE"), "Release", display_fn=_fmt_ms),
            PinnedParam(Symbol("MASTER_VOL"), "Volume", display_fn=_fmt_db),
        ),
    ),
)
