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

"""On-device UI for the x42-eq (fil4) parametric EQ plugin."""

from plugins.customization import PluginCustomization, register
from plugins.fil4.panel import Fil4Panel

FIL4_MONO_URI = "http://gareus.org/oss/lv2/fil4#mono"
FIL4_STEREO_URI = "http://gareus.org/oss/lv2/fil4#stereo"
FIL4_URIS = (FIL4_MONO_URI, FIL4_STEREO_URI)

register(*FIL4_URIS, customization=PluginCustomization(panel_cls=Fil4Panel))
