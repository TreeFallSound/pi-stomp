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

import fnmatch
import logging
import time
from typing import TypedDict

import rtmidi
from rtmidi import MidiOut as RtMidiOut

MidiMessage = list[int]

EXTERNAL_INSTANCE_ID = "External"

PORT_RETRY_BACKOFF_S = 5.0  # don't re-enumerate a failed port more often than this


class ExternalMidiOut:
    """
    Wrapper around external MIDI port that implements the same interface as
    the virtual port's midiout. Allows controls to send MIDI to external devices
    transparently, with automatic fallback to virtual port if device unavailable.
    """

    def __init__(self, external_midi_manager: ExternalMidiManager, port_name: str, fallback_midiout: RtMidiOut):
        self.external_midi = external_midi_manager
        self.port_name = port_name
        self.fallback = fallback_midiout

    def send_message(self, message: MidiMessage) -> None:
        try:
            success = self.external_midi.send_raw(self.port_name, message)
        except Exception:
            logging.warning(f"External MIDI send failed for port {self.port_name}, falling back to virtual")
            self.fallback.send_message(message)
            return
        if not success:
            self.fallback.send_message(message)


class PortConfig(TypedDict, total=False):
    auto_detect: list[str]
    port_index: int


class ExternalMidiConfig(TypedDict, total=False):
    enabled: bool
    send_delay_ms: int
    ports: dict[str, PortConfig]
    messages: dict[str, list[MidiMessage]]


class ExternalMidiManager:
    """
    Manages external MIDI device synchronization.
    Sends MIDI messages to external devices when pedalboards are loaded.
    """

    def __init__(self):
        self.midi_ports: dict[str, rtmidi.MidiOut] = {}
        self.port_configs: dict[str, PortConfig] = {}
        self.messages: dict[str, list[MidiMessage]] = {}
        self.enabled: bool = False
        self.send_delay_ms: int = 10
        self._open_failures: dict[str, float] = {}

    def update_config(self, cfg: ExternalMidiConfig | None) -> None:
        """
        Update configuration incrementally (can be called multiple times).
        Only updates fields that are present.
        """
        if cfg is None:
            return

        if "enabled" in cfg:
            self.enabled = cfg["enabled"]
            if self.enabled:
                logging.debug("External MIDI enabled")
            else:
                logging.debug("External MIDI disabled")

        if "send_delay_ms" in cfg:
            self.send_delay_ms = cfg["send_delay_ms"]

        if "ports" in cfg:
            # Deep merge: overlay individual port fields without replacing entire dicts
            for port_name, port_cfg in cfg["ports"].items():
                if port_name in self.port_configs:
                    self.port_configs[port_name] = {**self.port_configs[port_name], **port_cfg}
                else:
                    self.port_configs[port_name] = port_cfg

        if "messages" in cfg:
            # Merge messages at port level (replace entire message list per port)
            self.messages.update(cfg["messages"])

    def _get_available_ports(self) -> list[str]:
        try:
            temp_out = rtmidi.MidiOut()
            ports = temp_out.get_ports()
            del temp_out
            return ports
        except Exception as e:
            logging.error(f"Failed to enumerate MIDI ports: {e}")
            return []

    def _find_port_by_name(self, port_config: PortConfig) -> int | None:
        """
        Find MIDI port index matching a given config, returning its index if found.
        """
        if "port_index" in port_config:
            return port_config["port_index"]

        # Auto-detect by name patterns
        auto_detect = port_config.get("auto_detect", [])
        if not auto_detect:
            return None

        available_ports = self._get_available_ports()
        if not available_ports:
            return None

        # Search for matching ports using glob patterns
        matched_ports = []
        for pattern in auto_detect:
            for idx, port_name in enumerate(available_ports):
                # Case-insensitive glob matching
                if fnmatch.fnmatch(port_name.lower(), pattern.lower()):
                    matched_ports.append((idx, port_name))

        if not matched_ports:
            logging.warning(f"No MIDI ports matched patterns: {auto_detect}")
            return None

        # Warn if multiple matches
        if len(matched_ports) > 1:
            port_names = [name for _, name in matched_ports]
            logging.warning(
                f"Multiple MIDI ports matched {auto_detect}: {port_names}. Using first match: {matched_ports[0][1]}"
            )

        selected_idx, selected_name = matched_ports[0]
        logging.info(f"Auto-detected MIDI port: {selected_name} (index {selected_idx})")
        return selected_idx

    def open_port(self, port_name: str) -> bool:
        """Eagerly open a port at routing time so the first poll-loop send doesn't enumerate."""
        return self._init_port(port_name) is not None

    def _init_port(self, port_name: str) -> rtmidi.MidiOut | None:
        if port_name in self.midi_ports:
            return self.midi_ports[port_name]

        last_fail = self._open_failures.get(port_name)
        if last_fail is not None and (time.monotonic() - last_fail) < PORT_RETRY_BACKOFF_S:
            return None

        port_config = self.port_configs.get(port_name)
        if not port_config:
            logging.warning(f"No configuration found for MIDI port: {port_name}")
            self._open_failures[port_name] = time.monotonic()
            return None

        port_idx = self._find_port_by_name(port_config)
        if port_idx is None:
            logging.warning(f"Could not find MIDI port for: {port_name}")
            self._open_failures[port_name] = time.monotonic()
            return None

        try:
            midi_out = rtmidi.MidiOut()
            midi_out.open_port(port_idx)
            self.midi_ports[port_name] = midi_out
            self._open_failures.pop(port_name, None)
            logging.info(f"Opened MIDI port: {port_name}")
            return midi_out
        except Exception as e:
            logging.error(f"Failed to open MIDI port {port_name} (index {port_idx}): {e}")
            self._open_failures[port_name] = time.monotonic()
            return None

    def _invalidate_port(self, port_name: str) -> None:
        """
        Invalidate a port that has failed, closing it and removing from cache.
        This forces re-discovery/re-opening on next use.
        """
        if port_name in self.midi_ports:
            midi_out = self.midi_ports[port_name]
            try:
                midi_out.close_port()
            except Exception as e:
                logging.debug(f"Error closing invalidated port {port_name}: {e}")
            del self.midi_ports[port_name]
            self._open_failures[port_name] = time.monotonic()  # back off before re-enumerating

    def _validate_midi_message(self, message: MidiMessage) -> bool:
        if not isinstance(message, list) or len(message) < 2:
            logging.warning(f"Invalid MIDI message format (must be list with 2+ bytes): {message}")
            return False

        status = message[0]
        if not (0x80 <= status <= 0xFF):
            logging.warning(f"Invalid MIDI status byte (must be 0x80-0xFF): 0x{status:02X}")
            return False

        for i, byte in enumerate(message[1:], start=1):
            if not (0x00 <= byte <= 0x7F):
                logging.warning(f"Invalid MIDI data byte at position {i} (must be 0x00-0x7F): 0x{byte:02X}")
                return False

        return True

    def _send_messages(self, port_name: str, messages: list[MidiMessage], delay_ms: int = 10):
        midi_out = self._init_port(port_name)
        if midi_out is None:
            logging.warning(f"Skipping messages for unavailable port: {port_name}")
            return

        for i, message in enumerate(messages):
            if not self._validate_midi_message(message):
                logging.warning(f"Skipping invalid MIDI message {i + 1}/{len(messages)}: {message}")
                continue

            try:
                midi_out.send_message(message)
                logging.debug(f"Sent MIDI message to {port_name}: {[f'0x{b:02X}' for b in message]}")

                # Delay between messages (except after last one)
                if i < len(messages) - 1 and delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)

            except Exception as e:
                logging.error(f"Failed to send MIDI message to {port_name}: {e}")
                self._invalidate_port(port_name)
                break  # Stop sending remaining messages to this broken port

    def send_raw(self, port_name: str, message: MidiMessage) -> bool:
        """Send one raw message; True on success, False if the port is unavailable (caller falls back)."""
        if not self.enabled:
            return False

        if port_name not in self.port_configs:
            logging.error(f"Port '{port_name}' not found in external_midi config, falling back to virtual")
            return False

        midi_out = self._init_port(port_name)
        if midi_out is None:
            return False

        try:
            midi_out.send_message(message)
            return True
        except Exception as e:
            logging.error(f"Failed to send MIDI message to {port_name}: {e}")
            self._invalidate_port(port_name)
            return False

    def send_messages_for_pedalboard(self) -> bool:
        """Send the current pedalboard's external messages (config set earlier via update_config)."""
        if not self.enabled:
            return False

        if not self.messages:
            return False

        for port_name, messages in self.messages.items():
            if not messages:
                continue

            logging.debug(f"Sending MIDI message(s) to {port_name}: {messages}")
            self._send_messages(port_name, messages, self.send_delay_ms)

        return True

    def close(self):
        """Close ports and clean up."""
        for port_name, midi_out in self.midi_ports.items():
            try:
                midi_out.close_port()
                logging.debug(f"Closed MIDI port: {port_name}")
            except Exception as e:
                logging.warning(f"Error closing MIDI port {port_name}: {e}")

        self.midi_ports.clear()
        logging.info("External MIDI manager closed")
