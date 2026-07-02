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

"""Software-only stand-ins for the physical controls on pi-Stomp.

Each mock control subclasses the corresponding real hardware class so that
type checkers are satisfied, but bypasses any GPIO / SPI / ADC init.
"""

import time

import pistomp.analogcontrol as analogcontrol
import pistomp.analogmidicontrol as analogmidicontrol
import pistomp.controller as controller
import pistomp.encoder_controller as encoder_controller
from pistomp.encoder_controller import EncoderController
import pistomp.footswitch as footswitch
import pistomp.switchstate as switchstate

try:
    from rtmidi.midiconstants import CONTROL_CHANGE

    _rtmidi_available = True
except ImportError:
    _rtmidi_available = False
    CONTROL_CHANGE = 0xB0


class MockEncoder(encoder_controller.EncoderController):
    """Nav encoder (no GPIO).  Driven externally via step() / press()."""

    def __init__(self, type=None, id=None):
        super().__init__(d_pin=None, clk_pin=None, type=type, id=id)
        self.label: str | None = None

    def read_rotary(self):
        pass

    def step(self, direction):
        if direction != 0:
            self.refresh(direction)

    def get_display_info(self) -> controller.AnalogDisplayInfo:
        return {"type": self.type, "id": self.id, "category": None}

    def press(self, value):
        ts = time.monotonic()
        if value == switchstate.Value.LONGPRESSED:
            self._on_button_longpress(value, ts)
        else:
            self._on_button(value, ts)


class MockEncoderMidi(EncoderController):
    """Tweak encoder with MIDI CC.  Driven externally via step() / press()."""

    def __init__(self, midi_channel, midi_CC, type=None, id=None, cfg=None):
        super().__init__(d_pin=None, clk_pin=None,
                         midi_CC=midi_CC, midi_channel=midi_channel,
                         type=type, id=id)
        self.cfg = cfg or {'type': type, 'id': id}

    def read_rotary(self):
        pass

    def step(self, direction):
        self.refresh(direction)

    def press(self, value):
        ts = time.monotonic()
        if value == switchstate.Value.LONGPRESSED:
            self._on_button_longpress(value, ts)
        else:
            self._on_button(value, ts)


class MockFootswitch(footswitch.Footswitch):
    """Footswitch with no GPIO/ADC.  Driven externally via press()."""

    @classmethod
    def check_longpress_events(cls):
        pass

    def __init__(self, id, midi_CC, midi_channel, refresh_callback):
        # led_pin=None, pixel=None, gpio_input=None, adc_input=None — no GPIO paths taken
        super().__init__(id, None, None, midi_CC, midi_channel, refresh_callback)
        self.type = None
        self.cfg = {}

    def poll(self):
        pass

    def press(self):
        self.toggled = not self.toggled
        self.refresh_callback(footswitch=self)


class MockAnalogControl(analogmidicontrol.AnalogMidiControl):
    """Expression pedal / knob with no SPI/ADC.  Value set externally."""

    def __init__(self, midi_CC, midi_channel, control_type=None, id=None, cfg=None, midiout=None):
        super().__init__(spi=None, adc_channel=None, tolerance=0,
                         midi_CC=midi_CC, midi_channel=midi_channel,
                         type=control_type, id=id, cfg=cfg)
        self.midiout = midiout
        self.value = 64

    def refresh(self):
        pass

    def initialize(self):
        pass

    def set_midi_channel(self, midi_channel):
        self.midi_channel = midi_channel

    def set_value(self, value):
        self.value = int(value)
        self.last_read = int(value)

    def get_normalized_value(self) -> float:
        return self.last_read / 1023.0

    def send_midi(self, value_0_127):
        if self.midiout and self.midi_CC is not None and _rtmidi_available:
            self.midiout.send_message([CONTROL_CHANGE | (self.midi_channel & 0x0F), self.midi_CC, int(value_0_127)])
