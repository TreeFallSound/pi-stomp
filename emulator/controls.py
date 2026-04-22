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

"""Software-only stand-ins for the physical controls on pi-Stomp Tre.

Each mock control has the same interface that Hardware.poll_controls() expects
(read_rotary / poll / refresh) but does nothing on its own.  The emulator
window drives them by calling their step() / press() / set_value() methods.
"""

import logging

try:
    from rtmidi.midiconstants import CONTROL_CHANGE
    _rtmidi_available = True
except ImportError:
    _rtmidi_available = False
    CONTROL_CHANGE = 0xB0


class MockEncoder:
    """Nav encoder (no GPIO, no MIDI CC).  Driven externally via step()."""

    def __init__(self, callback, type=None, id=None):
        self.callback = callback
        self.press_callback = None   # set by EmulatorHardware after creation
        self.type = type
        self.id = id

    def read_rotary(self):
        pass

    def step(self, direction):
        if direction != 0 and self.callback:
            self.callback(direction)

    def press(self, value):
        if self.press_callback:
            self.press_callback(value)


class MockEncoderMidi:
    """Tweak encoder with MIDI CC.  Driven externally via step() / press()."""

    def __init__(self, handler, callback, midi_channel, midi_CC, midiout,
                 type=None, id=None, cfg=None):
        self.handler = handler
        self.callback = callback
        self.press_callback = None   # set by EmulatorHardware after creation
        self.midi_channel = midi_channel
        self.midi_CC = midi_CC
        self.midiout = midiout
        self.type = type
        self.id = id
        self.cfg = cfg or {'type': type, 'id': id}
        self.parameter = None
        self._midi_value = 64

    def read_rotary(self):
        pass

    def set_value(self, value):
        self._midi_value = int(value)

    def step(self, direction):
        self._midi_value = max(0, min(127, self._midi_value + direction))
        if self.midiout and self.midi_CC is not None and _rtmidi_available:
            self.midiout.send_message(
                [CONTROL_CHANGE | (self.midi_channel & 0x0F),
                 self.midi_CC, self._midi_value])
        if self.callback:
            self.callback(direction)

    def press(self, value):
        if self.press_callback:
            self.press_callback(value)


class MockFootswitch:
    """Footswitch with no GPIO/ADC.  Driven externally via press()."""

    # Match the Footswitch class-level interface expected by Hardware.reinit()
    all_longpress_groups = {}
    callbacks = {}

    @classmethod
    def init(cls, callbacks):
        cls.callbacks = callbacks

    @classmethod
    def check_longpress_events(cls):
        pass

    def __init__(self, id, midi_CC, midi_channel, midiout, refresh_callback):
        self.id = id
        self.midi_CC = midi_CC
        self.midi_channel = midi_channel
        self.midiout = midiout
        self.refresh_callback = refresh_callback
        self.enabled = False
        self.display_label = None
        self.lcd_color = None
        self.category = None
        self.longpress_groups = []
        self.relay_list = []
        self.preset_callback = None
        self.preset_callback_arg = None
        self.parameter = None
        self.type = None
        self.cfg = {}

    def get_display_label(self):
        return self.display_label or ""

    def poll(self):
        pass

    def press(self):
        self.enabled = not self.enabled
        if self.midiout and self.midi_CC is not None and _rtmidi_available:
            self.midiout.send_message(
                [CONTROL_CHANGE | (self.midi_channel & 0x0F),
                 self.midi_CC, 0 if self.enabled else 127])
        self.refresh_callback(footswitch=self)

    # --- interface expected by Hardware.reinit / bind_current_pedalboard -----

    def set_value(self, value):
        self.enabled = (value < 1)
        self.refresh_callback(footswitch=self)

    def set_midi_CC(self, cc):
        self.midi_CC = cc

    def set_midi_channel(self, ch):
        self.midi_channel = ch

    def set_display_label(self, label):
        self.display_label = label

    def set_lcd_color(self, color):
        self.lcd_color = color

    def set_category(self, category):
        self.category = category

    def set_longpress_groups(self, groups):
        if isinstance(groups, str):
            groups = groups.split()
        if isinstance(groups, list):
            self.longpress_groups = groups

    def clear_pedalboard_info(self):
        self.display_label = None
        self.lcd_color = None
        self.category = None
        self.preset_callback = None
        self.preset_callback_arg = None
        self.relay_list = []

    def clear_relays(self):
        self.relay_list = []

    def add_relay(self, relay):
        if relay:
            self.relay_list.append(relay)

    def add_preset(self, callback, callback_arg=None):
        self.preset_callback = callback
        self.preset_callback_arg = callback_arg


class MockAnalogControl:
    """Expression pedal / knob with no SPI/ADC.  Value set externally."""

    def __init__(self, midi_CC, midi_channel, midiout, control_type=None,
                 id=None, cfg=None):
        self.midi_CC = midi_CC
        self.midi_channel = midi_channel
        self.midiout = midiout
        self.type = control_type
        self.id = id
        self.cfg = cfg or {'type': control_type, 'id': id}
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
            self.midiout.send_message(
                [CONTROL_CHANGE | (self.midi_channel & 0x0F),
                 self.midi_CC, int(value_0_127)])
