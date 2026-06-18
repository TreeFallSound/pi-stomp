# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

from pathlib import Path

# Shared paths/constants used by the individual glyph modules.
FONTS_DIR: Path = Path(__file__).resolve().parent.parent.parent / "fonts"
DEFAULT_COLOR: tuple[int, int, int] = (255, 255, 255)

# Re-export glyphs for convenience
from uilib.glyphs.ethernet_cable import EthernetCableGlyph
from uilib.glyphs.expression_pedal import ExpressionPedalGlyph
from uilib.glyphs.keycap_corner import KeycapCornerGlyph
from uilib.glyphs.knob import KnobGlyph
from uilib.glyphs.pill import PillGlyph
from uilib.glyphs.signal_bars import SignalBarsGlyph

__all__ = [
    "DEFAULT_COLOR",
    "FONTS_DIR",
    "EthernetCableGlyph",
    "ExpressionPedalGlyph",
    "KeycapCornerGlyph",
    "KnobGlyph",
    "PillGlyph",
    "SignalBarsGlyph",
]
