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

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from pistomp.analogmidicontrol import AnalogMidiControl
from pistomp.controller import Controller
from pistomp.current import Current
from pistomp.encoder_controller import EncoderController
from pistomp.footswitch import Footswitch
from pistomp.footswitch_chords import FootswitchChords
from pistomp.input.event import ControllerEvent
from pistomp.input.sink import InputSink
from common.parameter import Symbol

if TYPE_CHECKING:
    from common.parameter import Parameter
    from modalapi.plugin import Plugin
    from modalapi.websocket_bridge import AsyncWebSocketBridge
    from pistomp.hardware import Hardware
    from pistomp.tuner.source import TunerSourceFactory


class Handler(InputSink):
    _ws_bridge: "AsyncWebSocketBridge | None" = None

    @property
    def ws_bridge(self) -> "AsyncWebSocketBridge":
        # Always constructed by MOD handlers in __init__; MIDI-only hosts never
        # access it. Assign via the setter (tests/subclasses set it directly).
        assert self._ws_bridge is not None, "WebSocket bridge has not been initialized"
        return self._ws_bridge

    @ws_bridge.setter
    def ws_bridge(self, bridge: "AsyncWebSocketBridge") -> None:
        self._ws_bridge = bridge

    def __init__(self):
        self.homedir = None
        self.lcd = None
        self.chord_helper = FootswitchChords()
        self._current: Current | None = None
        self._hardware: "Hardware | None" = None

    @property
    def current(self) -> Current:
        # Guaranteed set once a pedalboard is loaded (before the polling loop
        # runs). Use self._current for genuine "is a board loaded?" checks.
        assert self._current is not None, "No pedalboard is loaded"
        return self._current

    @current.setter
    def current(self, value: "Current | None") -> None:
        self._current = value

    @property
    def hardware(self) -> "Hardware":
        assert self._hardware is not None, "Hardware has not been initialized"
        return self._hardware

    @hardware.setter
    def hardware(self, value: "Hardware | None") -> None:
        self._hardware = value

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

    def open_parameter_dialog(self, parameter: "Parameter") -> None:
        """NAV CLICK on a selection resolving to a single symbol: open the
        same user-dismissable editor the generic plugin-parameter-menu uses.
        The dialog writes `parameter.value`, so a panel open underneath it
        repaints through its own subscription — no resync hook needed."""
        raise NotImplementedError()

    def open_parameter_submenu(self, plugin: "Plugin", rows: tuple[tuple[str, Symbol], ...], title: str) -> None:
        """NAV CLICK on a compound selection (e.g. an EQ band's gain/freq/Q):
        open a submenu over just these symbols, each row opening the same
        per-parameter dialog as open_parameter_dialog."""
        raise NotImplementedError()

    def open_audio_parameter_dialog(
        self, parameter: "Parameter", commit_callback: Callable[[str, float], None]
    ) -> None:
        """Same as open_parameter_dialog, for a synthetic audio-card
        parameter (no backing LV2 plugin, e.g. NAM's capture gain/volume)."""
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

    def handle(self, event: ControllerEvent) -> bool:
        raise NotImplementedError()

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
        # No-op fallback; Modhandler runs the Ethernet/JackBridge integration.
        pass

    def set_tuner_source_factory(self, factory: "TunerSourceFactory") -> None:
        pass

    def set_tuner_source_spec(self, spec: str) -> None:
        # No-op fallback for handlers without a tuner; Modhandler overrides.
        pass

    def is_symbol_locked(self, instance_id: str, symbol: Symbol) -> bool:
        return False

    def show_fullscreen_panel(self, plugin, panel_cls) -> None:
        pass

    def hide_fullscreen_panel(self) -> None:
        pass

    def _apply_midi_binding(
        self, instance: str, symbol: Symbol, binding: str, binding_range: tuple[float, float] | None = None
    ) -> None:
        # A MIDI mapping was learned in mod-ui. Update the matching parameter's
        # binding and wire its hardware controller so the LCD reflects it without
        # a pedalboard reload. Idempotent: replayed connect-dump maps are no-ops.
        if self._current is None:
            return
        plugin = next((p for p in self.current.pedalboard.plugins if p is not None and p.instance_id == instance), None)
        if plugin is None or plugin.parameters is None:
            return
        param = plugin.parameters.get(symbol)
        if param is None:
            return
        # The range can change without the binding (re-address the same CC to a
        # different sub-range), so apply it before the binding-unchanged bail.
        if binding_range is not None:
            param.set_binding_range(binding_range)
        if param.binding == binding:
            return
        controller = self.hardware.controllers.get(binding)
        if controller is None:
            return
        old_binding = param.binding
        param.binding = binding
        is_footswitch = self._bind_controller_to_param(plugin, param, controller)
        self._add_learned_binding_row(plugin, param, controller, old_binding)
        self._redraw_after_binding(controller, is_footswitch)

    def _bind_controller_to_param(self, plugin: "Plugin", param: "Parameter", controller: Controller) -> bool:
        # Wire a hardware controller to a plugin parameter. Returns True if the
        # controller is a footswitch (so callers can track footswitch plugins).
        controller.bind_to_parameter(param)
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

    def _add_learned_binding_row(
        self, plugin: "Plugin", param: "Parameter", controller: Controller, old_binding: str | None
    ) -> None:
        # Add a table row for a live-learned binding so dispatch and badges
        # reflect it without a pedalboard reload. MOD subclasses override;
        # non-MOD hosts never receive midi_map.
        pass
