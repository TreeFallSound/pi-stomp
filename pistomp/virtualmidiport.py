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

"""
Virtual MIDI port lifecycle management using amidithru.

Creates an ALSA virtual MIDI port, manages the subprocess,
and provides rtmidi access with proper cleanup.
"""

import logging
import subprocess
import time
import rtmidi
from typing import Optional


class VirtualMidiPort:
    """
    Manages a virtual ALSA MIDI port created via amidithru.

    Handles:
    - Subprocess lifecycle (creation, monitoring, cleanup)
    - Port discovery with retry/timeout
    - rtmidi connection management
    - Graceful shutdown
    """

    def __init__(self, port_name: str, timeout_sec: float = 2.0):
        """
        Create and connect to a virtual MIDI port.

        Args:
            port_name: Name for the virtual port (e.g., "piStomp-MIDI")
            timeout_sec: Max time to wait for port to appear

        Raises:
            RuntimeError: If port creation fails or timeout expires
        """
        self.port_name: str = port_name
        self.amidithru_process: subprocess.Popen | None = None
        self.midiout: rtmidi.MidiOut | None = None
        self._port_index: int | None = None

        self._create_virtual_port()
        self._wait_for_port(timeout_sec)
        self._connect_to_port()

        logging.info(f"Virtual MIDI port '{port_name}' ready at index {self._port_index}")

    def _create_virtual_port(self) -> None:
        """Start amidithru subprocess to create the virtual port."""
        try:
            self.amidithru_process = subprocess.Popen(
                ["/usr/local/bin/amidithru", self.port_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            logging.debug(f"Started amidithru process (PID {self.amidithru_process.pid})")
        except Exception as e:
            raise RuntimeError(f"Failed to start amidithru: {e}")

    def _wait_for_port(self, timeout_sec: float) -> None:
        """
        Poll for port to appear, with timeout.

        Args:
            timeout_sec: Maximum time to wait

        Raises:
            RuntimeError: If port doesn't appear within timeout
        """
        start_time = time.time()
        poll_interval = 0.1  # 100ms

        while time.time() - start_time < timeout_sec:
            port_index = self._find_port()
            if port_index is not None:
                self._port_index = port_index
                return
            time.sleep(poll_interval)

        # Timeout - cleanup and raise
        self.cleanup()
        raise RuntimeError(f"Virtual port '{self.port_name}' did not appear within {timeout_sec}s")

    def _find_port(self) -> Optional[int]:
        """
        Search for our virtual port in available MIDI ports.

        Returns:
            Port index if found, None otherwise
        """
        try:
            temp_midi = rtmidi.MidiOut()
            ports = temp_midi.get_ports()

            for i, port_name in enumerate(ports):
                if self.port_name in port_name:
                    logging.debug(f"Found port '{port_name}' at index {i}")
                    return i

            return None
        except Exception as e:
            logging.warning(f"Error searching for port: {e}")
            return None

    def _connect_to_port(self) -> None:
        """
        Open rtmidi connection to the virtual port.

        Raises:
            RuntimeError: If connection fails
        """
        try:
            self.midiout = rtmidi.MidiOut()
            self.midiout.open_port(self._port_index)
            logging.debug(f"Opened rtmidi connection to port {self._port_index}")
        except Exception as e:
            self.cleanup()
            raise RuntimeError(f"Failed to connect to virtual port: {e}")

    def get_midiout(self) -> rtmidi.MidiOut:
        """
        Get the rtmidi.MidiOut object for sending MIDI.

        Returns:
            rtmidi.MidiOut instance connected to the virtual port

        Raises:
            RuntimeError: If port is not initialized
        """
        if self.midiout is None:
            raise RuntimeError("Virtual MIDI port not initialized")
        return self.midiout

    def is_alive(self) -> bool:
        """Check if amidithru process is still running."""
        if self.amidithru_process is None:
            return False
        return self.amidithru_process.poll() is None

    def cleanup(self) -> None:
        """Clean up resources: close MIDI connection and terminate subprocess."""
        # Close rtmidi connection
        if self.midiout is not None:
            try:
                self.midiout.close_port()
                logging.debug("Closed rtmidi connection")
            except Exception as e:
                logging.warning(f"Error closing rtmidi: {e}")
            self.midiout = None

        # Terminate amidithru process
        if self.amidithru_process is not None:
            try:
                self.amidithru_process.terminate()
                self.amidithru_process.wait(timeout=2.0)
                logging.info(f"Terminated amidithru process (PID {self.amidithru_process.pid})")
            except subprocess.TimeoutExpired:
                logging.warning("amidithru did not terminate, killing...")
                self.amidithru_process.kill()
            except Exception as e:
                logging.warning(f"Error terminating amidithru: {e}")
            self.amidithru_process = None

    def __del__(self):
        """Ensure cleanup on garbage collection."""
        self.cleanup()

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.cleanup()
        return False
