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

"""WebSocket-based parameter setting for blend mode with MIDI de-duplication."""

import logging

from blend.types import ParameterKey, WebSocketBridgeProtocol


class ParameterSetter:
    """
    Sets plugin parameters via WebSocket with MIDI-level de-duplication.

    Tracks last-sent MIDI values per parameter to avoid redundant sends
    when smooth pedal movement produces consecutive identical MIDI values.
    """

    TOLERANCE = float(1 / 1024.0)

    def __init__(self, bridge: WebSocketBridgeProtocol) -> None:
        self.bridge = bridge
        self.last_sent_midi_values: dict[ParameterKey, float] = {}

    def send_parameter(self, instance_id: str, symbol: str, value: float) -> bool:
        """
        Send single parameter via WebSocket with de-duplication (non-blocking).

        Skips send if value hasn't changed (within 0.01 tolerance) since last send.
        This prevents flooding the WebSocket with redundant messages during smooth
        pedal movements.

        Returns True if message was sent, False if skipped due de-duplication or backpressure.
        """
        key = ParameterKey(instance_id, symbol)
        last_value = self.last_sent_midi_values.get(key)

        if last_value is not None and abs(last_value - value) < self.TOLERANCE:
            return False

        if self.bridge.send_parameter(instance_id, symbol, value):
            self.last_sent_midi_values[key] = value
            return True

        logging.warning(f"Dropped (backpressure): {instance_id}/{symbol} value={value:.3f}")
        return False

    def reset_tracking(self) -> None:
        self.last_sent_midi_values.clear()

    def cleanup(self) -> None:
        self.last_sent_midi_values.clear()
