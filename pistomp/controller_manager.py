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

import logging
from typing import TYPE_CHECKING

import common.token as Token
from common.contexts import (
    BindingDecl,
    CallbackEffect,
    ContextKind,
    ContextLayer,
    ContextRef,
    ContextStack,
    ControlClass,
    ControlRef,
    Effect,
    EventKind,
    LongpressActionConfig,
    MidiCcEffect,
    ParamEffect,
    PedalboardEffect,
    PresetEffect,
    RawMidiCcEffect,
    RelayEffect,
    ShadowState,
    TapTempoEffect,
)
from common.parameter import Parameter, PortInfo, Symbol, TTL_INTEGER
from modalapi.external_midi import EXTERNAL_INSTANCE_ID
from pistomp.analogmidicontrol import AnalogMidiControl
from pistomp.controller import AnalogDisplayInfo
from pistomp.current import Current
from pistomp.encoder_controller import ENCODER_FALLBACK_DEFAULT, EncoderController
from pistomp.footswitch import Footswitch

if TYPE_CHECKING:
    from pistomp.hardware import Hardware


class ControllerManager:
    """
    Manages controller/parameter bindings on the current pedalboard,
    overlaying per-pedalboard config on top of the base.
    The one genuine version difference is passed as a flag rather than subclassed:

      reorder_footswitch_plugins  v1 moves footswitch-controlled plugins to the
                                  tail of the chain; v3 leaves order untouched.
    """

    def __init__(self, hardware: "Hardware", *, reorder_footswitch_plugins: bool = False):
        self._hw = hardware
        self._reorder_footswitch_plugins = reorder_footswitch_plugins
        # Effective table (common/contexts.py, pistomp/input/README.md): the
        # PEDALBOARD layer of the resolved binding table, built alongside the
        # legacy dict outputs below. ORPHANED rows record TTL bindings with
        # no matching physical controller, which the legacy path drops
        # silently.
        self.effective_table = ContextStack(layers=[])

    def bind(self, current: Current | None) -> None:
        """Rebind all controllers for the active pedalboard state."""
        if current is None:
            return

        # Clear previous parameter bindings from all controllers except volume.
        for controller in self._hw.controllers.values():
            if controller.type != Token.VOLUME:
                controller.unbind_from_parameter()

        current.analog_controllers = {}
        pedalboard_layer = ContextLayer(ref=ContextRef(kind=ContextKind.PEDALBOARD))

        if current.pedalboard:
            footswitch_plugins = self._bind_plugin_parameters(current, pedalboard_layer)
            self._bind_volume_encoders(current)
            if self._reorder_footswitch_plugins:
                self._move_footswitch_plugins_to_end(current, footswitch_plugins)

        self._bind_external_controllers(current, pedalboard_layer)
        self._bind_encoder_longpress(pedalboard_layer)
        self._bind_footswitch_actions(pedalboard_layer)
        self.effective_table = ContextStack(layers=[pedalboard_layer])

    def _bind_plugin_parameters(self, current, pedalboard_layer: ContextLayer) -> list:
        """Bind controllers referenced by plugin parameters; return the plugins
        that gained a footswitch."""
        footswitch_plugins = []
        for plugin in current.pedalboard.plugins:
            if plugin is None or plugin.parameters is None:
                continue
            for param in plugin.parameters.values():
                if param.binding is None:
                    continue
                controller = self._hw.controllers.get(param.binding)
                if controller is None:
                    pedalboard_layer.add(
                        BindingDecl(
                            control=ControlRef(cls=ControlClass.ANALOG, id=param.binding),
                            event_kind=EventKind.ROTATE,
                            effects=(ParamEffect(plugin=plugin, symbol=param.symbol),),
                            context=pedalboard_layer.ref,
                            shadow_state=ShadowState.ORPHANED,
                        )
                    )
                    continue

                # External controllers aren't bound to plugin parameters.
                if self._hw.is_external(controller):
                    logging.warning(
                        f"Plugin parameter {plugin.name}:{param.name} is bound to external controller "
                        f"{param.binding} (routed to {self._hw.external_port_name(controller)}) - ignoring plugin binding"
                    )
                    continue

                controller.bind_to_parameter(param)
                plugin.controllers.append(controller)

                if isinstance(controller, Footswitch):
                    plugin.has_footswitch = True
                    footswitch_plugins.append(plugin)
                    controller.set_category(plugin.category)
                    event_kind = EventKind.PRESS
                    cls = ControlClass.FOOTSWITCH
                else:
                    key = "%s:%s" % (plugin.instance_id, param.name)
                    display_info = controller.get_display_info()
                    display_info["category"] = plugin.category
                    current.analog_controllers[key] = display_info
                    event_kind = EventKind.ROTATE
                    cls = ControlClass.ANALOG

                # the ParamEffect row must defer when tap tempo is active
                # N.B. closure captures the right taptempo instance for each row
                enabled_when = None
                if isinstance(controller, Footswitch) and controller.taptempo is not None:
                    _tap = controller.taptempo
                    enabled_when = lambda _tap=_tap: not _tap.is_enabled()  # noqa: E731

                pedalboard_layer.add(
                    BindingDecl(
                        control=ControlRef(cls=cls, id=param.binding),
                        event_kind=event_kind,
                        effects=(ParamEffect(plugin=plugin, symbol=param.symbol),),
                        context=pedalboard_layer.ref,
                        enabled_when=enabled_when,
                    )
                )
        return footswitch_plugins

    def _bind_volume_encoders(self, current) -> None:
        """Surface VOLUME-type encoders in the assignment display (v3 only in
        practice — v1 has no VOLUME-typed encoder)."""
        for e in self._hw.encoders:
            if e.type == Token.VOLUME:
                current.analog_controllers[Token.VOLUME] = e.get_display_info()

    @staticmethod
    def _move_footswitch_plugins_to_end(current, footswitch_plugins) -> None:
        plugins = current.pedalboard.plugins
        current.pedalboard.plugins = [p for p in plugins if p.has_footswitch is False] + footswitch_plugins

    def _bind_external_controllers(self, current, pedalboard_layer: ContextLayer) -> None:
        """Externally-routed controllers: bind a synthetic parameter and show
        them under an "External" category."""
        for controller in self._hw.controllers.values():
            if not self._hw.is_external(controller) or controller.midi_CC is None:
                continue
            port_name = self._hw.external_port_name(controller)
            key = f"{controller.midi_channel}:{controller.midi_CC}"

            if controller.parameter is None:
                if isinstance(controller, AnalogMidiControl):
                    controller.parameter = self._hw.create_external_parameter(
                        controller, port_name, controller.midi_channel, controller.midi_CC
                    )
                else:
                    ext_info = PortInfo(
                        name=f"{port_name} CC{controller.midi_CC}",
                        symbol=Symbol(f"external_{controller.midi_CC}"),
                        ranges={"minimum": 0, "maximum": 127},
                        properties=[TTL_INTEGER],
                    )
                    controller.bind_to_parameter(
                        Parameter(ext_info, ENCODER_FALLBACK_DEFAULT, key, EXTERNAL_INSTANCE_ID)
                    )

            pedalboard_layer.add(
                BindingDecl(
                    control=ControlRef(cls=ControlClass.ANALOG, id=key),
                    event_kind=EventKind.ROTATE,
                    effects=(MidiCcEffect(cc_ref=key),),
                    context=pedalboard_layer.ref,
                )
            )

            if isinstance(controller, Footswitch):
                # External footswitch: a CC toggle on PRESS, alongside the ROTATE
                # row above. Lives here (not in _bind_footswitch_actions) so the
                # external-routing boundary owns both rows for the same control.
                pedalboard_layer.add(
                    BindingDecl(
                        control=ControlRef(cls=ControlClass.FOOTSWITCH, id=key),
                        event_kind=EventKind.PRESS,
                        effects=(MidiCcEffect(cc_ref=key, toggle=True),),
                        context=pedalboard_layer.ref,
                    )
                )
                continue  # footswitches don't appear in the analog/encoder display

            entry: AnalogDisplayInfo = {
                **controller.get_display_info(),
                "port_name": port_name,
                "midi_cc": controller.midi_CC,
                "category": "External",
            }
            current.analog_controllers[key] = entry

    def _bind_encoder_longpress(self, pedalboard_layer: ContextLayer) -> None:
        """Encoders with a configured longpress callback get a LONGPRESS row keyed
        by their "channel:CC" identity — the same key the ROTATE rows use, so the
        resolver finds the callback by control + event_kind. VOLUME encoders and
        encoders without a midi_CC have no table presence and are skipped."""
        for enc in self._hw.encoders:
            if not isinstance(enc, EncoderController):
                continue
            if enc.midi_CC is None or enc.longpress is None:
                continue
            key = f"{enc.midi_channel}:{enc.midi_CC}"
            pedalboard_layer.add(
                BindingDecl(
                    control=ControlRef(cls=ControlClass.ANALOG, id=key),
                    event_kind=EventKind.LONGPRESS,
                    effects=(CallbackEffect(name=enc.longpress),),
                    context=pedalboard_layer.ref,
                )
            )

    def _bind_footswitch_actions(self, pedalboard_layer: ContextLayer) -> None:
        """Footswitch short-press actions (other than plugin-:bypass, which
        _bind_plugin_parameters already rows) become table rows so dispatch and
        badges share one authority. Config is mutually exclusive — a footswitch
        has at most one of preset / taptempo / midi_CC-toggle — so each gets
        exactly one PRESS row. External footswitches are rowed in
        _bind_external_controllers and skipped here.

        A footswitch with midi_CC is keyed by "channel:CC" (the same identity
        the ParamEffect PRESS rows use). A preset footswitch whose midi_CC was
        cleared by config is keyed by "fs:<slot>" — the dispatcher builds the
        same fallback from fs.id.

        Relay longpress is independent of the short-press action: a relay
        footswitch has both a PRESS row (CC toggle or plugin :bypass) and a
        LONGPRESS row (RelayEffect). It's added for any footswitch with a
        relay_list, regardless of its PRESS binding.

        Mapping-form longpress (`longpress: {midi_CC: 64}` etc., exclusive with
        the chord string/list form) rows a single LONGPRESS decl. The relay row
        is added first so it keeps precedence if both are present."""
        for fs in self._hw.footswitches:
            if self._hw.is_external(fs):
                continue  # owned by _bind_external_controllers

            key = fs.dispatch_key

            # Relay longpress: one relay today; the relays tuple is future schema.
            # Added before the PRESS-row skip so a plugin-bound relay footswitch
            # still gets its LONGPRESS row.
            if fs.relay_list:
                pedalboard_layer.add(
                    BindingDecl(
                        control=ControlRef(cls=ControlClass.FOOTSWITCH, id=key),
                        event_kind=EventKind.LONGPRESS,
                        effects=(RelayEffect(relays=("LEFT",)),),
                        context=pedalboard_layer.ref,
                    )
                )

            # Mapping-form longpress: dict config, parsed by Footswitch.
            lp = fs.longpress_action
            if lp is not None:
                pedalboard_layer.add(
                    BindingDecl(
                        control=ControlRef(cls=ControlClass.FOOTSWITCH, id=key),
                        event_kind=EventKind.LONGPRESS,
                        effects=self._longpress_action_effects(lp, fs),
                        context=pedalboard_layer.ref,
                    )
                )

            if fs.taptempo is not None:
                # Taptempo footswitch has two modes: stamp when enabled, CC toggle
                # when disabled. Two rows, gated by enabled_when so the resolver
                # picks the active one. The CC-toggle row carries the same midi_CC.
                # Must come before the plugin-:bypass guard so a footswitch with
                # both taptempo and a plugin binding still gets its TapTempoEffect row
                _tap = fs.taptempo
                pedalboard_layer.add(
                    BindingDecl(
                        control=ControlRef(cls=ControlClass.FOOTSWITCH, id=key),
                        event_kind=EventKind.PRESS,
                        effects=(TapTempoEffect(),),
                        context=pedalboard_layer.ref,
                        enabled_when=_tap.is_enabled,
                    )
                )
                if fs.midi_CC is not None:
                    pedalboard_layer.add(
                        BindingDecl(
                            control=ControlRef(cls=ControlClass.FOOTSWITCH, id=key),
                            event_kind=EventKind.PRESS,
                            effects=(MidiCcEffect(cc_ref=key, toggle=True),),
                            context=pedalboard_layer.ref,
                            enabled_when=lambda _tap=_tap: not _tap.is_enabled(),  # noqa: E731
                        )
                    )
                continue  # taptempo owns both rows; skip the elif chain below

            if fs.parameter is not None:
                continue  # plugin :bypass — _bind_plugin_parameters rowed it

            if fs.preset_direction is not None:
                pedalboard_layer.add(
                    BindingDecl(
                        control=ControlRef(cls=ControlClass.FOOTSWITCH, id=key),
                        event_kind=EventKind.PRESS,
                        effects=(PresetEffect(direction=fs.preset_direction),),
                        context=pedalboard_layer.ref,
                    )
                )
            elif fs.midi_CC is not None:
                pedalboard_layer.add(
                    BindingDecl(
                        control=ControlRef(cls=ControlClass.FOOTSWITCH, id=key),
                        event_kind=EventKind.PRESS,
                        effects=(MidiCcEffect(cc_ref=key, toggle=True),),
                        context=pedalboard_layer.ref,
                    )
                )

    @staticmethod
    def _longpress_action_effects(lp: LongpressActionConfig, fs: Footswitch) -> tuple[Effect, ...]:
        """Translate a mapping-form longpress dict into a single-effect tuple.
        The schema guarantees exactly one key."""
        if "midi_CC" in lp:
            return (RawMidiCcEffect(channel=fs.midi_channel, cc=int(lp["midi_CC"])),)
        if "preset" in lp:
            return (PresetEffect(direction=str(lp["preset"])),)
        if "pedalboard" in lp:
            return (PedalboardEffect(direction=str(lp["pedalboard"])),)
        return ()
