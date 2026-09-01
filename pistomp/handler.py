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

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from pistomp.current import Current
from pistomp.footswitch_chords import FootswitchChords
from pistomp.input.event import ControllerEvent
from pistomp.input.sink import InputSink
from common.parameter import Symbol

if TYPE_CHECKING:
    from common.parameter import Parameter
    from modalapi.plugin import Plugin
    from modalapi.websocket_bridge import AsyncWebSocketBridge
    from pistomp.hardware import Hardware
    from pistomp.settings import Settings
    from pistomp.tuner.source import TunerSourceFactory


class Handler(InputSink):
    _ws_bridge: "AsyncWebSocketBridge | None" = None
    settings: "Settings"

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

    def _fire_longpress_groups(self, fs) -> None:
        """Resolve a matured footswitch longpress and run what it named."""
        for name in self.chord_helper.observe(fs):
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
        # A MIDI mapping was learned or cleared in mod-ui. Record it on the
        # parameter and re-derive the board: param.binding is the source the
        # activation builds from, so there is no second wiring path to keep in
        # step. Idempotent — replayed connect-dump maps are no-ops.
        if self._current is None:
            return
        plugin = self.current.pedalboard.find_plugin(instance)
        if plugin is None or plugin.parameters is None:
            return
        param = plugin.parameters.get(symbol)
        if param is None:
            return

        is_unmapped = binding in ("-1:-1", "-1")
        controller = None if is_unmapped else self.hardware.controllers.get(binding)

        # The range can change without the binding (re-address the same CC to a
        # different sub-range), so apply it before the binding-unchanged bail.
        # On unmap, restore the plugin's declared LV2 range.
        if is_unmapped:
            param.clear_binding_range()
        elif binding_range is not None:
            param.set_binding_range(binding_range)

        # A CC with no physical control is a real external device's mapping: keep
        # its range, but adopt no binding — there is nothing here to wire.
        new_binding = binding if controller is not None else None
        if param.binding == new_binding:
            return

        # Externally-routed controls aren't bound to plugin parameters; board
        # load ignores such bindings (_bind_plugin_parameters) and the live
        # learn must agree, or the control's MidiCcEffect row shadows the
        # learned row and commits emit raw values out the external port.
        if controller is not None and self.hardware.is_external(controller):
            logging.warning(
                f"MIDI learn for {instance}:{param.name} names external controller "
                f"{binding} (routed to {self.hardware.external_port_name(controller)}) - ignoring"
            )
            return

        param.binding = new_binding
        self._rebind_pedalboard()

    def _rebind_pedalboard(self) -> None:
        """Build the board's associations and rows again. A handler that owns an
        activation must override this."""
        raise NotImplementedError()


