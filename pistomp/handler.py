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

from typing import Any

import common.token as Token
from pistomp.analogmidicontrol import AnalogMidiControl
from pistomp.encodermidicontrol import EncoderMidiControl
from pistomp.footswitch import Footswitch
from pistomp.tuner.source import TunerSourceFactory


class Handler:
    def __init__(self):
        self.homedir = None
        self.lcd = None
        self.hardware: Any = None
        self.current: Any = None

    @property
    def lcd_poll_divisor(self) -> int:
        # Gate for poll_lcd_updates, in units of 10 ms main-loop ticks
        # (20 → one flush every 200 ms). Subclasses may override to narrow
        # it dynamically (e.g. when the tuner panel is visible).
        return 20

    def noop(self):
        pass

    def update_lcd_fs(self, footswitch=None, bypass_change=False):
        raise NotImplementedError()

    def add_lcd(self, lcd):
        raise NotImplementedError()

    def add_hardware(self, hardware):
        raise NotImplementedError()

    def poll_controls(self):
        raise NotImplementedError()

    def poll_modui_changes(self):
        raise NotImplementedError()

    def poll_ws_messages(self):
        # no-op for handlers without a WS
        pass

    def preset_incr_and_change(self):
        raise NotImplementedError()

    def preset_decr_and_change(self):
        raise NotImplementedError()

    def top_encoder_select(self, direction):
        raise NotImplementedError()

    def top_encoder_sw(self, value):
        raise NotImplementedError()

    def bot_encoder_select(self, direction):
        raise NotImplementedError()

    def bottom_encoder_sw(self, value):
        raise NotImplementedError()

    def universal_encoder_select(self, direction):
        raise NotImplementedError()

    def universal_encoder_sw(self, value):
        raise NotImplementedError()

    def cleanup(self):
        raise NotImplementedError()

    def get_num_footswitches(self):
        raise NotImplementedError()

    def get_callback(self, callback_name):
        raise NotImplementedError()

    def set_mod_tap_tempo(self, bpm):
        raise NotImplementedError()

    def load_banks(self):
        raise NotImplementedError()

    def poll_indicators(self):
        raise NotImplementedError()

    def poll_lcd_updates(self):
        raise NotImplementedError()

    def poll_wifi(self):
        raise NotImplementedError()

    def set_tuner_source_factory(self, factory: "TunerSourceFactory") -> None:
        pass

    #
    # MIDI binding (shared by v1/v3 handlers)
    #
    def _apply_midi_binding(self, instance, symbol, binding):
        # A MIDI mapping was learned in mod-ui. Update the matching parameter's
        # binding and wire its hardware controller so the LCD reflects it without
        # a pedalboard reload. Idempotent: replayed connect-dump maps are no-ops.
        if self.current is None:
            return
        plugin = next((p for p in self.current.pedalboard.plugins
                       if p is not None and p.instance_id == instance), None)
        if plugin is None or plugin.parameters is None:
            return
        param = plugin.parameters.get(symbol)
        if param is None or param.binding == binding:
            return
        controller = self.hardware.controllers.get(binding)
        if controller is None:
            return
        param.binding = binding
        is_footswitch = self._bind_controller_to_param(plugin, param, controller)
        self._redraw_after_binding(controller, is_footswitch)

    def _bind_controller_to_param(self, plugin, param, controller) -> bool:
        # Wire a hardware controller to a plugin parameter. Returns True if the
        # controller is a footswitch (so callers can track footswitch plugins).
        # TODO possibly use a setter instead of accessing var directly
        # What if multiple params could map to the same controller?
        controller.parameter = param  # pyright: ignore[reportAttributeAccessIssue]
        controller.set_value(param.value)
        if controller not in plugin.controllers:
            plugin.controllers.append(controller)
        if isinstance(controller, Footswitch):
            # TODO sort this list so selection orders correctly (sort on midi_CC?)
            plugin.has_footswitch = True
            controller.set_category(plugin.category)
            return True
        elif isinstance(controller, (AnalogMidiControl, EncoderMidiControl)):
            key = "%s:%s" % (plugin.instance_id, param.name)
            controller.cfg[Token.CATEGORY] = plugin.category  # somewhat LAME adding to cfg dict
            controller.cfg[Token.TYPE] = controller.type
            controller.cfg[Token.ID] = controller.id
            self.current.analog_controllers[key] = controller.cfg
        return False

    def _redraw_after_binding(self, controller, is_footswitch):
        # Refresh the LCD after a learned binding. Subclasses redraw at their
        # own granularity.
        raise NotImplementedError()
