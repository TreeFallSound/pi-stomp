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

"""Invada compressor: mono and stereo share LV2 ports; both get the a-comp-derived panel."""

from __future__ import annotations

from plugins.customization import PluginCustomization, register
from plugins.invadacompressor.panel import InvadaCompressorPanel

INVADA_COMPRESSOR_MONO_URI = "http://invadarecords.com/plugins/lv2/compressor/mono"
INVADA_COMPRESSOR_STEREO_URI = "http://invadarecords.com/plugins/lv2/compressor/stereo"

_customization = PluginCustomization(
    panel_cls=InvadaCompressorPanel,
    display_name="Invada Compressor",
)

register(INVADA_COMPRESSOR_MONO_URI, customization=_customization)
register(INVADA_COMPRESSOR_STEREO_URI, customization=_customization)
