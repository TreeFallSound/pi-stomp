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

from collections import deque

TAP_TEMPO_SAMPLES = 4       # number of samples to consider in calculation, higher can skew the average for higher tempos
TAP_TEMPO_RESET_TIME = 1.5    # seconds between samples after which we should consider clearing the (likely stale) samples
TAP_TEMPO_MINIMUM = 60 / TAP_TEMPO_RESET_TIME

class TapTempo:

    def __init__(self, callback=None):
        self.timestamps = deque()
        self.taptempo = 0
        self.callback = callback
        self.enabled = False

    def __calc_tempo(self):
        if len(self.timestamps) < 2:
            return  # Not enough timestamps to calculate tempo

        # Calculate the time difference between the most recent and the oldest timestamp
        time_difference = self.timestamps[-1] - self.timestamps[0]

        # if the last two were more than a few seconds apart, clear and start fresh
        # (only check if time_difference is also greater than that threshold to avoid the extra computation)
        if time_difference > TAP_TEMPO_RESET_TIME and self.timestamps[-1] - self.timestamps[-2] > TAP_TEMPO_RESET_TIME:
            current = self.timestamps.pop()
            self.timestamps.clear()
            self.timestamps.append(current)
            return

        # Calculate the average time difference between consecutive timestamps
        average_time_difference = time_difference / (len(self.timestamps) - 1)

        # Calculate the tempo in beats per minute (BPM)
        self.taptempo = round(60 / average_time_difference, 2)

        # Call the callback if it's not None
        if self.taptempo >= TAP_TEMPO_MINIMUM and self.callback:
            self.callback(self.taptempo)

    def set_callback(self, callback):
        self.callback = callback

    def enable(self, enable):
        self.enabled = enable

    def is_enabled(self):
        return self.enabled

    def toggle_enable(self):
        self.enabled = not self.enabled

    def get_bpm(self):
        return self.taptempo

    def set_bpm(self, bpm):
        # this is to set the initial bpm as obtained from the handler
        self.taptempo = bpm

    def stamp(self, t):
        if not self.enabled:
            return
        self.timestamps.append(t)
        if len(self.timestamps) > TAP_TEMPO_SAMPLES:
            self.timestamps.popleft()
        self.__calc_tempo()

