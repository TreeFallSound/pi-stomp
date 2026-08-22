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

import logging
import os
import sys

from common.parameter import Parameter, PortInfo, Symbol, TTL_INTEGER
import pistomp.analogmidicontrol as AnalogMidiControl
import pistomp.config as config
import pistomp.encoder_controller as EncoderController
import pistomp.footswitch as Footswitch
import pistomp.taptempo as taptempo

from abc import ABC, abstractmethod
from modalapi.external_midi import ExternalMidiManager, EXTERNAL_INSTANCE_ID
from pistomp.input.sink import InputSink
from pistomp.controller import Controller, RoutingInfo
from pistomp.config.model import (
    AnalogBinding,
    EncoderBinding,
    FootswitchBinding,
    PedalboardConfig,
    PresetStep,
)
from pistomp.config.schema_v1 import ConfigDocument
import pistomp.relay as Relay


class Hardware(ABC):
    def __init__(self, default_config, handler, midiout, refresh_callback):
        logging.info("Init hardware: " + type(self).__name__)
        self.handler = handler
        self.midiout = midiout
        self.refresh_callback = refresh_callback
        self.spi = None
        self.test_pass = False
        self.test_sentinel = None

        self.default_cfg: ConfigDocument = default_config
        self.config = config.resolve(default_config)
        self.version = self.config.version
        self.midi_channel = self.config.midi_channel

        # Standard hardware objects (not required to exist)
        self.relay: Relay.Relay | None = None
        self.analog_controls: list[AnalogMidiControl.AnalogMidiControl] = []
        self.encoders = []
        self.controllers: dict[str, Controller] = {}
        self.footswitches: list[Footswitch.Footswitch] = []
        self.indicators = []
        self.debounce_map = None
        self.ledstrip = None
        self.taptempo = taptempo.TapTempo(None)
        self.external_midi: ExternalMidiManager | None = None
        # control → destination; absent means internal (virtual/mod-host).
        # Rebuilt every reinit. Identity-keyed; controllers are stable across
        # reinit (mutated in place).
        self.external_routing: dict[Controller, RoutingInfo] = {}

    def register_sink(self, sink: InputSink) -> None:
        """Assign `sink` as the default dispatch target for every controller
        owned by this hardware. Called by Handler.add_hardware after this
        Hardware is fully constructed."""
        for ac in self.analog_controls:
            if isinstance(ac, Controller):
                ac.sink = sink
        for enc in self.encoders:
            enc.sink = sink
        for fs in self.footswitches:
            fs.sink = sink

    def toggle_tap_tempo_enable(self, bpm: float = 0.0):
        if self.taptempo:
            self.taptempo.toggle_enable()
            if self.taptempo.is_enabled() and bpm > 0:
                self.taptempo.set_bpm(bpm)
                logging.debug("tap tempo mode enabled: %f", bpm)

    def init_spi(self):
        import spidev

        self.spi = spidev.SpiDev()
        self.spi.open(0, 1)  # Bus 0, CE1
        self.spi.max_speed_hz = 1_000_000

    def poll_controls(self):
        # This is intended to be called periodically from main working loop to poll the instantiated controls
        for c in self.analog_controls:
            c.refresh()
        for e in self.encoders:
            e.read_rotary()
            if hasattr(e, "poll"):
                e.poll()
        for s in self.footswitches:
            s.poll()

    def sync_analog_controls(self):
        """Send current values of analog controls with autosync enabled via MIDI."""
        for control in self.analog_controls:
            if isinstance(control, AnalogMidiControl.AnalogMidiControl) and control.autosync:
                try:
                    control.send_current_value()
                except Exception as e:
                    logging.warning(f"Failed to sync analog control {control.midi_CC}: {e}")

    def is_external(self, controller: Controller) -> bool:
        return controller in self.external_routing

    def external_port_name(self, controller: Controller) -> str | None:
        info = self.external_routing.get(controller)
        return info.port_name if info is not None else None

    def poll_indicators(self):
        for i in self.indicators:
            i.refresh()

    def recalibrateVU_gain(self, input_gain):
        for i in self.indicators:
            i.recalibrate_gain(input_gain)

    def recalibrateVU_baseline(self, baseline):
        for i in self.indicators:
            i.recalibrate_baseline(baseline)

    def reinit(self, config: PedalboardConfig) -> None:
        self.config = config
        self.midi_channel = config.midi_channel
        self.external_routing.clear()
        self.controllers.clear()
        self.handler.chord_helper.rebuild(self.handler.callbacks)

        if self.external_midi is not None:
            self.external_midi.set_config(config.external_midi)

        for fs in self.footswitches:
            binding = config.footswitch(fs.id) if fs.id is not None else None
            if binding is not None:
                self.__apply_footswitch(fs, binding)
            self.handler.chord_helper.register(fs)

        for enc in self.encoders:
            binding = config.encoder(enc.id) if enc.id is not None else None
            if binding is not None:
                self.__apply_encoder(enc, binding)

        for ac in self.analog_controls:
            binding = config.analog_control(ac.id) if ac.id is not None else None
            if binding is not None:
                self.__apply_analog_control(ac, binding)

    @abstractmethod
    def init_analog_controls(self): ...

    @abstractmethod
    def init_encoders(self): ...

    @abstractmethod
    def init_footswitches(self): ...

    @abstractmethod
    def init_relays(self): ...

    @abstractmethod
    def cleanup(self): ...

    @abstractmethod
    def test(self): ...

    def run_test(self):
        # if test sentinel file exists execute hardware test
        script_dir = os.path.dirname(os.path.realpath(__file__))
        self.test_sentinel = os.path.join(script_dir, ".hardware_tests_passed")
        if not os.path.isfile(self.test_sentinel):
            self.test_pass = False
            self.test()

    def create_footswitches(self, config: PedalboardConfig) -> None:
        bindings = [b for b in config.footswitches if not b.disable]
        if not bindings:
            return

        uses_ledstrip = self.ledstrip is not None and any(b.ledstrip_position is not None for b in bindings)
        if uses_ledstrip:
            assert self.ledstrip is not None
            ledstrip_gpio = self.ledstrip.get_gpio()
            if ledstrip_gpio in [b.gpio_output for b in bindings]:
                logging.error(
                    "Config file error. A gpio_output cannot use the GPIO of the ledstrip at ledstrip_position"
                )
                sys.exit()

        for b in bindings:
            gpio_input = b.gpio_input
            if self.debounce_map and b.debounce_input in self.debounce_map:
                gpio_input = self.debounce_map[b.debounce_input]

            if b.adc_input is None and gpio_input is None:
                logging.error("Config file error. Footswitch %d has no adc_input, gpio_input or debounce_input", b.id)
                continue

            pixel = None
            if self.ledstrip is not None and b.ledstrip_position is not None:
                pixel = self.ledstrip.add_pixel(b.id, b.ledstrip_position)

            switch_taptempo = None
            if b.tap_tempo is not None:
                switch_taptempo = self.taptempo
                switch_taptempo.set_callback(self.handler.get_callback(b.tap_tempo))

            if b.adc_input is not None:
                fs = Footswitch.Footswitch(
                    b.id,
                    b.gpio_output,
                    pixel,
                    b.midi_CC,
                    b.midi_channel,
                    refresh_callback=self.refresh_callback,
                    adc_input=b.adc_input,
                    spi=self.spi,
                    taptempo=switch_taptempo,
                )
            else:
                fs = Footswitch.Footswitch(
                    b.id,
                    b.gpio_output,
                    pixel,
                    b.midi_CC,
                    b.midi_channel,
                    refresh_callback=self.refresh_callback,
                    gpio_input=gpio_input,
                    taptempo=switch_taptempo,
                )
            logging.debug("Created Footswitch %d, Midi Chan: %d, CC: %s", b.id, b.midi_channel, b.midi_CC)
            self.footswitches.append(fs)
            self.register_controller(fs)

    def create_analog_controls(self, config: PedalboardConfig) -> None:
        for b in config.analog_controls:
            if b.disable:
                continue
            if b.adc_input is None:
                logging.error("Config file error. Analog control %d has no adc_input", b.id)
                continue
            if b.midi_CC is None:
                logging.error("Config file error. Analog control %d has no midi_CC", b.id)
                continue

            control = AnalogMidiControl.AnalogMidiControl(
                self.spi, b.adc_input, b.threshold, b.midi_CC, b.midi_channel, b.type, b.id, b.autosync
            )
            self.analog_controls.append(control)
            self.register_controller(control)
            logging.debug(
                "Created AnalogMidiControl Input: %d, Midi Chan: %d, CC: %d", b.adc_input, b.midi_channel, b.midi_CC
            )

    @abstractmethod
    def add_encoder(
        self, id, type, longpress_callback, midi_channel, midi_cc
    ) -> EncoderController.EncoderController | None:
        # This should be implemented by hardware subclasses that support tweak encoders (Tre at least)
        ...

    def create_encoders(self, config: PedalboardConfig) -> None:
        for b in config.encoders:
            if b.disable:
                continue
            try:
                control = self.add_encoder(b.id, b.type, b.longpress, b.midi_channel, b.midi_CC)
            except Exception:
                logging.exception("Failed to create encoder %d", b.id)
                continue
            # FIXME: add_encoder returns None for emulator v1/v2 stubs that don't
            # implement config-driven encoders, forcing the return type to be optional.
            if control is not None:
                self.encoders.append(control)
                self.register_controller(control)
                logging.debug("Created Encoder: %d, Midi Chan: %d, CC: %s", b.id, b.midi_channel, b.midi_CC)

    def create_external_parameter(self, port_name, midi_channel, midi_cc, initial_value: int = 0):
        name = f"{port_name}:{midi_cc}"
        info = PortInfo(
            name=name,
            symbol=Symbol(f"external_{port_name}_{midi_cc}"),
            ranges={"minimum": 0, "maximum": 127},
            properties=[TTL_INTEGER],
        )
        return Parameter(info, initial_value, f"{midi_channel}:{midi_cc}", EXTERNAL_INSTANCE_ID)

    def __validate_midi_port(self, port_name):
        if self.external_midi is None:
            logging.warning(f"midi_port '{port_name}' set but external_midi not initialized, falling back to virtual")
            return None
        return port_name

    def register_controller(self, control: Controller) -> None:
        if control.midi_CC is not None:
            self.controllers["%d:%d" % (control.midi_channel, control.midi_CC)] = control

    def __route(self, control: Controller, midi_port: str | None) -> None:
        port = self.__validate_midi_port(midi_port) if midi_port else None
        if port is None or self.external_midi is None:
            self.external_routing.pop(control, None)
            return
        self.external_midi.open_port(port)
        self.external_routing[control] = RoutingInfo.external(port)

    def __apply_footswitch(self, fs: Footswitch.Footswitch, binding: FootswitchBinding) -> None:
        fs.toggled = False
        fs.disabled = binding.disable
        fs.parameter = None
        fs.set_display_label(None)
        fs.set_category(None)
        fs.clear_relays()
        fs.add_preset(direction=None, callback_arg=None)
        fs.set_lcd_color(binding.color)
        fs.set_longpress_groups(binding.longpress)
        fs.set_midi_channel(binding.midi_channel)
        fs.set_midi_CC(binding.midi_CC)

        if binding.uses_relay:
            if self.relay is not None:
                fs.add_relay(self.relay)
                fs.set_display_label("byps")
            else:
                logging.warning("Footswitch %s bypass config ignored, no relay hardware", binding.id)

        if binding.preset is not None:
            fs.set_midi_CC(None)
            if isinstance(binding.preset, PresetStep):
                fs.add_preset(direction=binding.preset.value)
                fs.set_display_label("Pre+" if binding.preset is PresetStep.UP else "Pre-")
            else:
                fs.add_preset(direction=str(binding.preset), callback_arg=binding.preset)
                fs.set_display_label(str(binding.preset))

        self.register_controller(fs)
        self.__route(fs, binding.midi_port)

    def __apply_encoder(self, enc: Controller, binding: EncoderBinding) -> None:
        enc.midi_channel = binding.midi_channel
        enc.midi_CC = binding.midi_CC
        if isinstance(enc, EncoderController.EncoderController):
            enc.set_longpress(binding.longpress)
        self.register_controller(enc)
        self.__route(enc, binding.midi_port)

    def __apply_analog_control(self, control: Controller, binding: AnalogBinding) -> None:
        control.midi_channel = binding.midi_channel
        control.midi_CC = binding.midi_CC
        if isinstance(control, AnalogMidiControl.AnalogMidiControl):
            control.autosync = binding.autosync
        self.register_controller(control)
        self.__route(control, binding.midi_port)
