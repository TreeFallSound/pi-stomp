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


# Type alias for MIDI message (list of bytes)
MidiMessage = list[int]


class PortConfig(TypedDict, total=False):
    """Configuration for a MIDI port."""

    auto_detect: list[str]
    port_index: int


class ExternalMidiConfig(TypedDict, total=False):
    """External MIDI configuration (part of hardware config)."""

    enabled: bool
    send_delay_ms: int
    ports: dict[str, PortConfig]
    messages: dict[str, list[MidiMessage]]  # port_name -> list of MIDI messages


class ExternalMidiManager:
    """
    Manages external MIDI device synchronization.
    Sends MIDI messages to external devices when pedalboards are loaded.
    """

    def __init__(self):
        """
        Initialize the External MIDI Manager.
        Configuration will be provided via update_config() method.
        """
        self.midi_ports: dict[str, rtmidi.MidiOut | None] = {}
        self.port_configs: dict[str, PortConfig] = {}
        self.messages: dict[str, list[MidiMessage]] = {}
        self.enabled: bool = False
        self.send_delay_ms: int = 10

    def update_config(self, cfg: ExternalMidiConfig | None) -> None:
        """
        Update configuration incrementally (can be called multiple times).
        Follows the same pattern as footswitch config - only updates fields that are present.

        Called from hardware.reinit():
        - First with default config (sets everything)
        - Then with pedalboard config (overlays only what's specified)

        Args:
            cfg: External MIDI configuration from hardware config, or None to skip.
        """
        if cfg is None:
            return

        # Update only fields that are present (incremental pattern)
        if "enabled" in cfg:
            self.enabled = cfg["enabled"]
            if self.enabled:
                logging.debug("External MIDI enabled")
            else:
                logging.debug("External MIDI disabled")

        if "send_delay_ms" in cfg:
            self.send_delay_ms = cfg["send_delay_ms"]

        if "ports" in cfg:
            # Merge ports (port-level granularity)
            self.port_configs.update(cfg["ports"])

        if "messages" in cfg:
            # Merge messages at port level
            # This allows pedalboard config to override specific ports while keeping others
            self.messages.update(cfg["messages"])
            logging.debug(f"Updated external MIDI messages for ports: {list(cfg['messages'].keys())}")

    def _get_available_ports(self) -> list[str]:
        """
        Get list of available MIDI output port names.

        Returns:
            List of available port names.
        """
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
        Find MIDI port index by auto-detection patterns.

        Args:
            port_config: Port configuration with auto_detect patterns (glob-style).

        Returns:
            Port index if found, None otherwise.
        """
        # Check for manual port_index override
        if "port_index" in port_config:
            return port_config["port_index"]

        # Auto-detect by name patterns
        auto_detect = port_config.get("auto_detect", [])
        if not auto_detect:
            return None

        available_ports = self._get_available_ports()
        if not available_ports:
            return None

        # Log available ports for debugging
        logging.debug(f"Available MIDI ports: {available_ports}")

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

    def _init_port(self, port_name: str) -> rtmidi.MidiOut | None:
        """
        Lazy initialization of MIDI port.

        Args:
            port_name: Name of port configuration from config file.

        Returns:
            MidiOut object if successful, None otherwise.
        """
        # Check if already initialized
        if port_name in self.midi_ports:
            return self.midi_ports[port_name]

        # Get port configuration
        port_config = self.port_configs.get(port_name)
        if not port_config:
            logging.warning(f"No configuration found for MIDI port: {port_name}")
            self.midi_ports[port_name] = None
            return None

        # Find the port
        port_idx = self._find_port_by_name(port_config)
        if port_idx is None:
            logging.warning(f"Could not find MIDI port for: {port_name}")
            self.midi_ports[port_name] = None
            return None

        # Open the port
        try:
            midi_out = rtmidi.MidiOut()
            midi_out.open_port(port_idx)
            self.midi_ports[port_name] = midi_out
            logging.info(f"Opened MIDI port: {port_name}")
            return midi_out
        except Exception as e:
            logging.error(f"Failed to open MIDI port {port_name} (index {port_idx}): {e}")
            self.midi_ports[port_name] = None
            return None

    def _validate_midi_message(self, message: MidiMessage) -> bool:
        """
        Validate MIDI message format.

        Args:
            message: MIDI message as list of integers.

        Returns:
            True if valid, False otherwise.
        """
        if not isinstance(message, list) or len(message) < 2:
            logging.warning(f"Invalid MIDI message format (must be list with 2+ bytes): {message}")
            return False

        # Check status byte (must be 0x80-0xFF)
        status = message[0]
        if not (0x80 <= status <= 0xFF):
            logging.warning(f"Invalid MIDI status byte (must be 0x80-0xFF): 0x{status:02X}")
            return False

        # Check data bytes (must be 0x00-0x7F)
        for i, byte in enumerate(message[1:], start=1):
            if not (0x00 <= byte <= 0x7F):
                logging.warning(f"Invalid MIDI data byte at position {i} (must be 0x00-0x7F): 0x{byte:02X}")
                return False

        return True

    def _send_messages(self, port_name: str, messages: list[MidiMessage], delay_ms: int = 10):
        """
        Send MIDI messages to a port.

        Args:
            port_name: Name of port configuration.
            messages: List of MIDI messages to send.
            delay_ms: Delay between messages in milliseconds.
        """
        # Lazy initialization of port
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

    def send_messages_for_pedalboard(self) -> bool:
        """
        Send external MIDI messages for current pedalboard configuration.
        Configuration should have been set via update_config() before calling this.

        Returns:
            True if messages were sent successfully, False otherwise.
        """
        if not self.enabled:
            return False

        if not self.messages:
            return False

        # Send messages to each configured port
        for port_name, messages in self.messages.items():
            if not messages:
                logging.debug(f"No messages configured for port {port_name}, skipping")
                continue

            logging.info(f"Sending {len(messages)} MIDI message(s) to {port_name}")
            self._send_messages(port_name, messages, self.send_delay_ms)

        return True

    def close(self):
        """
        Close all MIDI ports and cleanup resources.
        """
        # Close external MIDI ports
        for port_name, midi_out in self.midi_ports.items():
            if midi_out is not None:
                try:
                    midi_out.close_port()
                    logging.debug(f"Closed MIDI port: {port_name}")
                except Exception as e:
                    logging.warning(f"Error closing MIDI port {port_name}: {e}")

        self.midi_ports.clear()
        logging.info("External MIDI manager closed")
