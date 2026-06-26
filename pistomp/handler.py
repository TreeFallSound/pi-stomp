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

from typing import TYPE_CHECKING

from pistomp.analogmidicontrol import AnalogMidiControl
from pistomp.current import Current
from pistomp.encoder_controller import EncoderController
from pistomp.footswitch import Footswitch
from pistomp.footswitch_chords import FootswitchChords
from pistomp.input.event import ControllerEvent, SwitchEventKind
from pistomp.input.sink import InputSink
from pistomp.tuner.source import TunerSourceFactory

if TYPE_CHECKING:
    from modalapi.websocket_bridge import AsyncWebSocketBridge
    from pistomp.hardware import Hardware


class Handler(InputSink):
    ws_bridge: "AsyncWebSocketBridge | None" = None

    def __init__(self):
        self.homedir = None
        self.lcd = None
        self.chord_helper = FootswitchChords()
        self.current: Current | None = None

    @property
    def hardware(self) -> "Hardware": ...

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

    def handle(self, event: ControllerEvent) -> bool:
        raise NotImplementedError()

    # ── Footswitch dispatch (shared by v1/v3) ────────────────────────────

    def _handle_footswitch(self, fs: "Footswitch", kind: SwitchEventKind, timestamp: float) -> bool:
        """Resolve a footswitch SwitchEvent. Mirrors the old Footswitch.pressed()
        behavior exactly, but as the sole arbiter on the handler side."""
        if kind == SwitchEventKind.LONGPRESS:
            if fs.relay_list:
                # Relay footswitch: longpress toggles the relay immediately and
                # never enters chord resolution.
                new_toggled = not fs.toggled
                fs.toggled = new_toggled
                fs.toggle_relays(new_toggled)
                fs.set_led(new_toggled)
                self.update_lcd_fs(bypass_change=True)
            else:
                # TODO: consider case where relay and longpress are specified
                self.chord_helper.observe(fs, timestamp)
            return True

        # Short press
        if fs.taptempo and fs.taptempo.is_enabled():
            fs.taptempo.stamp(timestamp)
            return True
        if fs.preset_callback is not None:
            if fs.preset_callback_arg is not None:
                fs.preset_callback(fs.preset_callback_arg)
            else:
                fs.preset_callback()
            return True
        if fs.midi_CC is not None:
            fs.toggled = not fs.toggled
            fs.set_led(fs.toggled)
            self._emit_midi(fs, 127 if fs.toggled else 0)
        if fs.parameter is not None:
            fs.parameter.value = not fs.toggled  # FIXME: assumes mapped parameter is :bypass
        self.update_lcd_fs(footswitch=fs)
        return True

    def _tick_chords(self) -> None:
        """Resolve pending footswitch chords/singletons. Call once per poll cycle."""
        for name in self.chord_helper.tick():
            cb = self.get_callback(name)
            if cb:
                cb()

    def _emit_midi(self, controller, midi_value: int) -> None:
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

    def pedalboard_change(self, pedalboard: Any) -> None:
        raise NotImplementedError()

    def poll_indicators(self):
        raise NotImplementedError()

    def poll_lcd_updates(self):
        raise NotImplementedError()

    def poll_wifi(self):
        raise NotImplementedError()

    def poll_ethernet(self):
        # v1/v2 handlers don't run the Ethernet/JackBridge integration.
        pass

    def set_tuner_source_factory(self, factory: "TunerSourceFactory") -> None:
        pass

    def is_symbol_locked(self, instance_id: str, symbol: str) -> bool:
        return False

    def show_fullscreen_panel(self, plugin, panel_cls) -> None:
        pass

    def hide_fullscreen_panel(self) -> None:
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
        plugin = next((p for p in self.current.pedalboard.plugins if p is not None and p.instance_id == instance), None)
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
        elif isinstance(controller, (AnalogMidiControl, EncoderController)):
            key = "%s:%s" % (plugin.instance_id, param.name)
            display_info = controller.get_display_info()
            display_info["category"] = plugin.category
            self.current.analog_controllers[key] = display_info
        return False

    def _redraw_after_binding(self, controller, is_footswitch):
        # Refresh the LCD after a learned binding. Subclasses redraw at their
        # own granularity.
        raise NotImplementedError()
