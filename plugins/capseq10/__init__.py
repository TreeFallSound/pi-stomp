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

"""Registration for the caps-Eq10 plugin and its stereo build, Eq10X2.

Eq10X2 exposes the identical ten control ports; only the audio pinout differs,
so both share the one graphic-EQ panel.
"""

from plugins.customization import PluginCustomization, register
from plugins.capseq10.panel import CapsEq10Panel

CAPSEQ10_URI = "http://moddevices.com/plugins/caps/Eq10"
CAPSEQ10X2_URI = "http://moddevices.com/plugins/caps/Eq10X2"

register(
    CAPSEQ10_URI,
    customization=PluginCustomization(
        panel_cls=CapsEq10Panel,
        display_name="caps-Eq10",
    ),
)

register(
    CAPSEQ10X2_URI,
    customization=PluginCustomization(
        panel_cls=CapsEq10Panel,
        display_name="caps-Eq10X2",
    ),
)
