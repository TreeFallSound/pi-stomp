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

from pathlib import Path
from PIL import ImageFont

from common.fonts import FONTS_DIR

_orig_truetype = ImageFont.truetype


def _resolve_truetype(font=None, size=10, **kwargs):
    if font is None:
        font = str(FONTS_DIR / "DejaVuSans.ttf")
    elif isinstance(font, str) and not Path(font).is_absolute() and not Path(font).exists():
        candidate = FONTS_DIR / font
        if candidate.exists():
            font = str(candidate)
    return _orig_truetype(font, size, **kwargs)


ImageFont.truetype = _resolve_truetype
