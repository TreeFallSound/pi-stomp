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

"""Which hardware inputs the user turned on, kept across pedalboards.

This is a device fact, not a config fact: it says what is plugged in, so it
lives in settings.yml and not in a config file that the user owns. An
EXPRESSION input is off until the user turns it on, because an empty jack
reads ADC noise. Every other control is on until the user turns it off.

The id space is the screen position that `draw_analog_assignments` paints, so
one analog control and one encoder never share an id.
"""

from __future__ import annotations

from pistomp.controller import ControlType
from pistomp.settings import Settings

SETTING = "input_enabled"


class InputEnable:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        stored = settings.get_setting(SETTING)
        self._choices: dict[int, bool] = (
            {int(k): bool(v) for k, v in stored.items()} if isinstance(stored, dict) else {}
        )

    def is_enabled(self, control_id: int | None, control_type: ControlType) -> bool:
        if control_id is None:
            return True
        chosen = self._choices.get(control_id)
        if chosen is None:
            return control_type is not ControlType.EXPRESSION
        return chosen

    def set_enabled(self, control_id: int, enabled: bool) -> None:
        self._choices[control_id] = enabled
        self._settings.set_setting(SETTING, dict(self._choices))
