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

"""Registration for the CAPS Noisegate plugin.

Control ports (from the plugin TTL):
  open    dB threshold to open the gate   (-60 .. 0,    default -45)
  attack  attack time in ms               (  0 .. 5,    default   0)
  close   dB threshold to close the gate  (-80 .. 0,    default -67.5)
  mains   mains frequency in Hz, 0 = auto (  0 .. 100,  default  50)
"""

from __future__ import annotations

from common.parameter import Symbol
from modalapi.plugin_customization import PinnedParam
from plugins.customization import PluginCustomization, register

CAPS_NOISEGATE_URI = "http://moddevices.com/plugins/caps/Noisegate"


def _fmt_db(value: float) -> tuple[str, str]:
    return f"{value:+.0f}", "dB"


def _fmt_ms(value: float) -> tuple[str, str]:
    return f"{value:.0f}", "ms"


def _fmt_mains(value: float) -> tuple[str, str]:
    return ("auto", "") if value == 0.0 else (f"{value:.0f}", "Hz")


register(
    CAPS_NOISEGATE_URI,
    customization=PluginCustomization(
        display_name="CAPS Noisegate",
        pinned_params=(
            PinnedParam(Symbol("open"), "Open", display_fn=_fmt_db),
            PinnedParam(Symbol("close"), "Close", display_fn=_fmt_db),
            PinnedParam(Symbol("attack"), "Attack", display_fn=_fmt_ms),
            PinnedParam(Symbol("mains"), "Mains", display_fn=_fmt_mains),
        ),
    ),
)
