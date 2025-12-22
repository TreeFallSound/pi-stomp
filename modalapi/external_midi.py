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
import subprocess
import time
from pathlib import Path
from typing import TypedDict

import yaml
import rtmidi


class PortConfig(TypedDict, total=False):
    """Configuration for a MIDI port."""

    auto_detect: list[str]
    port_index: int


class PortMessageConfig(TypedDict, total=False):
    """Configuration for messages sent to a port."""

    port: str
    messages: list[list[int]]
    delay_ms: int


class SettingsConfig(TypedDict, total=False):
    """Global settings configuration."""

    enabled: bool
    send_delay_ms: int


PedalboardMappings = dict[str, list[PortMessageConfig]]
MidiPorts = dict[str, PortConfig]


class ExternalMidiManager:
    """
    Manages external MIDI device synchronization.
    Sends MIDI messages to external devices when pedalboards are loaded.
    """

    def __init__(self, data_dir: str, config_path: str | None = None):
        """
        Initialize the External MIDI Manager.

        Args:
            data_dir: Data directory path (required).
            config_path: Optional path to config file. If None, uses default location.
        """
        self.data_dir: str = data_dir
        self.config_path: str | None = config_path
        self.config: SettingsConfig = {}
        self.midi_ports: dict[str, rtmidi.MidiOut | None] = {}
        self.port_configs: MidiPorts = {}
        self.enabled: bool = False
        self.virtual_midi_out: rtmidi.MidiOut | None = None
        self.amidithru_process: subprocess.Popen | None = None

        # Load configuration
        if self.load_config():
            # Config loaded successfully - feature is enabled
            logging.info("External MIDI synchronization enabled (lazy port initialization)")

        # Create virtual MIDI port using amidithru (so MOD can see it)
        # This allows routing through LV2 MIDI plugins in the MOD pedalboard
        try:
            # Start amidithru process to create the ALSA port
            self.amidithru_process = subprocess.Popen(
                ["/usr/local/bin/amidithru", "piStomp-Expression"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logging.info("Started amidithru process for piStomp-Expression")

            # Wait a moment for the port to be created
            time.sleep(0.5)

            # Connect to the amidithru port with rtmidi to send messages
            self.virtual_midi_out = rtmidi.MidiOut()
            ports = self.virtual_midi_out.get_ports()

            # Find the piStomp-Expression port
            target_port = None
            for i, port_name in enumerate(ports):
                if "piStomp-Expression" in port_name:
                    target_port = i
                    break

            if target_port is not None:
                self.virtual_midi_out.open_port(target_port)
                logging.info(f"Connected to virtual MIDI port: {ports[target_port]}")
            else:
                logging.warning("Could not find piStomp-Expression port to connect")
                self.virtual_midi_out = None

        except Exception as e:
            logging.warning(f"Failed to create virtual MIDI port: {e}")
            if self.amidithru_process:
                self.amidithru_process.terminate()
                self.amidithru_process = None
            self.virtual_midi_out = None

    def load_config(self) -> bool:
        """
        Load configuration from file.
        Checks multiple locations in order of priority.

        Returns:
            True if config loaded successfully, False otherwise.
        """
        config_locations = []

        # Use explicit path if provided
        if self.config_path:
            config_locations.append(self.config_path)
        else:
            # Default location: data_dir/config/external_midi.yml
            config_locations.append(Path(self.data_dir) / "config" / "external_midi.yml")

        # Try each location
        for config_file in config_locations:
            config_file = Path(config_file)
            if config_file.exists():
                try:
                    with open(config_file, "r") as f:
                        self.config = yaml.safe_load(f) or {}

                    # Validate and extract settings
                    settings = self.config.get("settings", {})
                    self.enabled = settings.get("enabled", True)

                    if not self.enabled:
                        logging.info(f"External MIDI disabled in config: {config_file}")
                        return False

                    # Store port configurations for lazy initialization
                    self.port_configs = self.config.get("midi_ports", {})

                    logging.info(f"External MIDI config loaded from: {config_file}")
                    return True

                except Exception as e:
                    logging.warning(f"Failed to load external MIDI config from {config_file}: {e}")
                    self.enabled = False
                    return False

        # No config found - disable feature silently
        self.enabled = False
        return False

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

    def _validate_midi_message(self, message: list[int]) -> bool:
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

    def _match_pedalboard(self, pedalboard) -> list[PortMessageConfig] | None:
        """
        Find matching MIDI configuration for a pedalboard.
        Uses priority: exact bundle path > exact title > glob pattern title > default.

        Args:
            pedalboard: Pedalboard object with .bundle and .title attributes.

        Returns:
            List of port message configurations, or None if no match.
        """
        pedalboard_mappings: PedalboardMappings = self.config.get("pedalboards", {})
        if not pedalboard_mappings:
            return None

        bundle_path = pedalboard.bundle
        title = pedalboard.title

        # Priority 1: Exact bundle path match
        if bundle_path in pedalboard_mappings:
            logging.debug(f"Matched pedalboard by bundle path: {bundle_path}")
            return pedalboard_mappings[bundle_path]

        # Priority 2: Exact title match
        if title in pedalboard_mappings:
            logging.debug(f"Matched pedalboard by exact title: {title}")
            return pedalboard_mappings[title]

        # Priority 3: Glob pattern title match (longest match wins)
        # Skip 'default' key during pattern matching
        matched_patterns = []
        for pattern, config in pedalboard_mappings.items():
            if pattern != "default" and fnmatch.fnmatch(title, pattern):
                matched_patterns.append((pattern, config))

        if matched_patterns:
            # Sort by pattern length (descending) to get most specific match
            matched_patterns.sort(key=lambda x: len(x[0]), reverse=True)
            matched_pattern, matched_config = matched_patterns[0]
            logging.debug(f"Matched pedalboard by glob pattern '{matched_pattern}': {title}")
            return matched_config

        # Priority 4: Default configuration (if exists)
        if "default" in pedalboard_mappings:
            logging.info(f"Using default MIDI configuration for pedalboard: {title}")
            return pedalboard_mappings["default"]

        # No match
        logging.debug(f"No external MIDI mapping for pedalboard: {title}")
        return None

    def _send_messages(self, port_name: str, messages: list[list[int]], delay_ms: int = 10):
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

    def send_passthrough_cc(self, source_channel: int, source_cc: int, value: int) -> bool:
        """
        Send MIDI CC message to virtual port for routing in MOD pedalboard.

        Args:
            source_channel: Source MIDI channel (0-15, where 0 = channel 1).
            source_cc: Source MIDI CC number (0-127).
            value: CC value (0-127).

        Returns:
            True if message was sent, False otherwise.
        """
        # Send MIDI message to virtual port - MOD handles all routing from there
        if self.virtual_midi_out is not None:
            try:
                status_byte = 0xB0 | (source_channel & 0x0F)
                message = [status_byte, source_cc & 0x7F, value & 0x7F]
                self.virtual_midi_out.send_message(message)
                logging.debug(
                    f"Sent to virtual port: CH{source_channel + 1} CC{source_cc} = {value}"
                )
                return True
            except Exception as e:
                logging.warning(f"Failed to send to virtual MIDI port: {e}")
                return False

        return False

    def send_messages_for_pedalboard(self, pedalboard) -> bool:
        """
        Send external MIDI messages for a pedalboard load.

        Args:
            pedalboard: Pedalboard object with .bundle and .title attributes.

        Returns:
            True if messages were sent successfully, False otherwise.
        """
        if not self.enabled:
            return False

        port_configs = self._match_pedalboard(pedalboard)
        if not port_configs:
            return False

        settings: SettingsConfig = self.config.get("settings", {})
        default_delay = settings.get("send_delay_ms", 10)

        for port_config in port_configs:
            port_name = port_config.get("port")
            messages = port_config.get("messages", [])
            delay = port_config.get("delay_ms", default_delay)

            if not port_name:
                logging.warning("Port configuration missing 'port' field, skipping")
                continue

            if not messages:
                logging.debug(f"No messages configured for port {port_name}, skipping")
                continue

            logging.info(f"Sending {len(messages)} MIDI message(s) to {port_name} for pedalboard: {pedalboard.title}")
            self._send_messages(port_name, messages, delay)

        return True

    def close(self):
        """
        Close all MIDI ports and cleanup resources.
        """
        # Close virtual MIDI port
        if self.virtual_midi_out is not None:
            try:
                self.virtual_midi_out.close_port()
                logging.debug("Closed virtual MIDI port: piStomp-Expression")
            except Exception as e:
                logging.warning(f"Error closing virtual MIDI port: {e}")
            self.virtual_midi_out = None

        # Terminate amidithru process
        if self.amidithru_process is not None:
            try:
                self.amidithru_process.terminate()
                self.amidithru_process.wait(timeout=2)
                logging.debug("Terminated amidithru process")
            except Exception as e:
                logging.warning(f"Error terminating amidithru process: {e}")
                try:
                    self.amidithru_process.kill()
                except:
                    pass
            self.amidithru_process = None

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
