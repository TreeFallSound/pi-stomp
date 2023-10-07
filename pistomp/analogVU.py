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


import pistomp.analogcontrol as AnalogControl
import logging

from collections import deque
from enum import Enum

SAMPLE_PERIOD_MS = 10
AVERAGE_PERIOD_SAMPLES = 4
AVERAGE_PERIOD_OFF = 50

class VuState(Enum):
    OFF = 0
    SIG = 1
    WARN = 2
    CLIP = 3

class AnalogVU(AnalogControl.AnalogControl):

    def __init__(self, spi, adc_channel, tolerance, ledstrip, ledstrip_pos, input_gain):
        super(AnalogVU, self).__init__(spi, adc_channel, tolerance)
        self.ledstrip = ledstrip
        self.pixel = ledstrip.add_pixel(None, ledstrip_pos)
        self.pixel.set_enable(False)

        # The idea here is to have two sampling windows, one for the "on" states (SIG, WARN, CLIP)
        # one for the "off" state.  To avoid a flickery display, the off should have a longer period (some delay)
        # where "on" states should be immediate since they are likely transient and won't last long
        self.samples = deque([0]*AVERAGE_PERIOD_SAMPLES, maxlen=AVERAGE_PERIOD_SAMPLES)  # Use a deque with a maximum length
        self.off = deque([0]*AVERAGE_PERIOD_OFF, maxlen=AVERAGE_PERIOD_OFF)  # Use a deque with a maximum length

        self.last_avg = 0
        self.state = VuState.OFF
        self.color_map = {VuState.OFF: None, VuState.SIG: "forestgreen", VuState.WARN: "orange", VuState.CLIP: "red"}

        # TODO baseline (zero signal) will likely be unique to specific ADC/Opamp
        # Should at least let user set it
        #self.adc_baseline = self.readChannel()
        self.adc_baseline = 520
        self.units_per_volt = 512 / 1.665   # ADC units/2 / supplyVoltage/2

        self.thresh_sig = 0
        self.thresh_warn = 0
        self.thresh_clip = 0

        self.recalibrate(input_gain)

    def recalibrate(self, input_gain):
        # This should get called when user changes ALSA capture_volume (aka input gain)
        # Since the ADC reading the input level is before any input gain adjustment,
        # The thresholds must change to accommodate the input gain.
        # Positive input gain, means lower thresholds since the input will clip at lower levels
        # Negative input gain, means higher thresholds since the ADC will receive less signal

        # Threshold in db   dbV = 20 log (db)
        # TODO Make these threshold values user configurable via default_config.yml

        thresh_sig_db = -39 - input_gain
        self.thresh_sig = int(self.adc_baseline + ((10 ** (thresh_sig_db / 20)) * self.units_per_volt))

        thresh_warn_db = -20 - input_gain
        self.thresh_warn = int(self.adc_baseline + ((10 ** (thresh_warn_db / 20)) * self.units_per_volt))

        thresh_clip_db = -15 - input_gain
        self.thresh_clip = int(self.adc_baseline + ((10 ** (thresh_clip_db / 20)) * self.units_per_volt))

        logging.debug("analogVU thresholds: Signal Present: %d, Warn: %d, Clip: %d" %
                      (thresh_sig_db, thresh_warn_db, thresh_clip_db))

    def calculate_average_amplitude(self, samples):
        if len(samples) == 0:
            return 0.0
        return sum(samples) / len(samples)  # TODO keep running sum instead of this O(n)

    def change_color(self, state):
        if self.state is VuState.OFF:
            self.pixel.set_enable(False)
        else:
            self.pixel.set_color(self.color_map[state])
            self.pixel.set_enable(True)

    def refresh(self):
        # read the analog pin
        value = self.readChannel()

        value = abs(self.adc_baseline - value) + self.adc_baseline
        self.samples.append(value)
        self.off.append(value)

        average_amplitude = self.calculate_average_amplitude(self.samples)
        average_off = self.calculate_average_amplitude(self.off)

        # Off condition (more samples/lag than On)
        state = self.state
        if 500 < average_off < self.thresh_sig:
            state = VuState.OFF

        # On condition
        elif average_amplitude != self.last_avg:
            if self.thresh_sig <= average_amplitude < self.thresh_warn:  # was 523, 540, 560
                state = VuState.SIG
            elif self.thresh_warn <= average_amplitude < self.thresh_clip:
                state = VuState.WARN
            elif average_amplitude >= self.thresh_clip:
                state = VuState.CLIP

            self.last_avg = average_amplitude

        # Only change LED if the state changed
        if state != self.state:
            self.state = state
            self.change_color(state)
