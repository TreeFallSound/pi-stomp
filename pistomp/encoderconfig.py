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

from __future__ import annotations

from typing import TypedDict, Any
import common.util as Util


class ShortpressCallbackConfig(TypedDict, total=False):
    """Configuration for shortpress callback with arguments."""

    callback: str
    args: Any


# Union type for shortpress: can be string or dict
ShortpressConfig = str | ShortpressCallbackConfig


class EncoderConfig(TypedDict, total=False):
    """Configuration for an encoder from YAML config file."""

    id: int
    type: str
    midi_CC: int
    longpress: str
    shortpress: ShortpressConfig
    disable: bool


class ParsedShortpress:
    """Parsed shortpress configuration with normalized fields."""

    def __init__(
        self,
        callback_name: str | None = None,
        callback_arg: Any = None
    ):
        self.callback_name = callback_name
        self.callback_arg = callback_arg


def parse_shortpress_config(
    shortpress_config: ShortpressConfig | None,
    default_callback_name: str = "universal_encoder_sw"
) -> ParsedShortpress:
    """Parse shortpress config, enriching string to object form."""
    if shortpress_config is None:
        return ParsedShortpress(callback_name=default_callback_name)

    if isinstance(shortpress_config, str):
        return ParsedShortpress(callback_name=shortpress_config)

    if isinstance(shortpress_config, dict):
        callback_name = Util.DICT_GET(shortpress_config, 'callback')
        callback_arg = Util.DICT_GET(shortpress_config, 'args')

        if callback_name is None and callback_arg is not None:
            callback_name = default_callback_name

        return ParsedShortpress(callback_name=callback_name, callback_arg=callback_arg)

    return ParsedShortpress(callback_name=default_callback_name)
