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

"""CAPS Compress: full-screen panel with live GR meter."""

from __future__ import annotations

from plugins.caps_compress.panel import CapsCompressPanel
from plugins.customization import PluginCustomization, register

CAPS_COMPRESS_URI = "http://moddevices.com/plugins/caps/Compress"
CAPS_COMPRESSX2_URI = "http://moddevices.com/plugins/caps/CompressX2"

register(
    CAPS_COMPRESS_URI,
    CAPS_COMPRESSX2_URI,
    customization=PluginCustomization(
        panel_cls=CapsCompressPanel,
        display_name="CAPS Compress",
    ),
)
