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

import pistomp.analogcontrol as analogcontrol
import pistomp.encoder as encoder
import pistomp.encodermidicontrol as encodermidicontrol
import pistomp.footswitch as footswitch

try:
    from rtmidi.midiconstants import CONTROL_CHANGE

    _rtmidi_available = True
except ImportError:
    _rtmidi_available = False
    CONTROL_CHANGE = 0xB0


class MockEncoder(encoder.Encoder):
    """Nav encoder (no GPIO).  Driven externally via step() / press()."""

    def __init__(self, callback, type=None, id=None):
        super().__init__(d_pin=None, clk_pin=None, callback=callback, type=type, id=id)
        self.press_callback = None
        self.label: str | None = None

    def read_rotary(self):
        pass

    def step(self, direction):
        if direction != 0 and self.callback:
            self.callback(direction)

    def press(self, value):
        if self.press_callback:
            self.press_callback(value)


class MockEncoderMidi(encodermidicontrol.EncoderMidiControl):
    """Tweak encoder with MIDI CC.  Driven externally via step() / press()."""

    def __init__(self, handler, callback, midi_channel, midi_CC, midiout, type=None, id=None, cfg=None):
        super().__init__(
            handler=handler,
            d_pin=None,
            clk_pin=None,
            callback=callback,
            midi_CC=midi_CC,
            midi_channel=midi_channel,
            midiout=midiout,
            type=type,
            id=id,
        )
        self.cfg = cfg or {"type": type, "id": id}
        self.midi_value = 64
        self.press_callback = None
        self._user_callback = callback

    def read_rotary(self):
        pass

    def set_value(self, value):
        self.midi_value = int(value)

    def step(self, direction):
        self.midi_value = max(0, min(127, self.midi_value + direction))
        if self.midiout and self.midi_CC is not None and _rtmidi_available:
            self.midiout.send_message([CONTROL_CHANGE | (self.midi_channel & 0x0F), self.midi_CC, self.midi_value])
        if self._user_callback:
            self._user_callback(direction)

    def press(self, value):
        if self.press_callback:
            self.press_callback(value)


class MockFootswitch(footswitch.Footswitch):
    """Footswitch with no GPIO/ADC.  Driven externally via press()."""

    @classmethod
    def check_longpress_events(cls):
        pass

    def __init__(self, id, midi_CC, midi_channel, midiout, refresh_callback):
        # led_pin=None, pixel=None, gpio_input=None, adc_input=None — no GPIO paths taken
        super().__init__(id, None, None, midi_CC, midi_channel, midiout, refresh_callback)
        self.type = None
        self.cfg = {}

    def poll(self):
        pass

    def press(self):
        self.toggled = not self.toggled
        if self.midiout and self.midi_CC is not None and _rtmidi_available:
            self.midiout.send_message(
                [CONTROL_CHANGE | (self.midi_channel & 0x0F), self.midi_CC, 127 if self.toggled else 0]
            )
        self.refresh_callback(footswitch=self)


class MockAnalogControl(analogcontrol.AnalogControl):
    """Expression pedal / knob with no SPI/ADC.  Value set externally."""

    def __init__(self, midi_CC, midi_channel, midiout, control_type=None, id=None, cfg=None):
        # AnalogControl.__init__ only stores spi/channel/tolerance — safe with None
        super().__init__(spi=None, adc_channel=None, tolerance=0)
        self.midi_CC = midi_CC
        self.midi_channel = midi_channel
        self.midiout = midiout
        self.type = control_type
        self.id = id
        self.cfg = cfg or {"type": control_type, "id": id}
        self.value = 64
        self.parameter = None

    def refresh(self):
        pass

    def initialize(self):
        pass

    def set_midi_channel(self, ch):
        self.midi_channel = ch

    def set_value(self, value):
        self.value = int(value)

    def send_midi(self, value_0_127):
        if self.midiout and self.midi_CC is not None and _rtmidi_available:
            self.midiout.send_message([CONTROL_CHANGE | (self.midi_channel & 0x0F), self.midi_CC, int(value_0_127)])
