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

import logging
import os
import subprocess
import threading
import time
from typing import Optional

# Hard-coded interface name: every pi-stomp board ships with the onboard NIC as
# `end0` under predictable interface naming. If a future variant differs, lift
# this to config rather than scrubbing sysfs.
IFACE = "end0"
SERVICE = "pi-stomp-jackbridge.service"
# Contract with the JackBridge service: truncate-on-start, atomic-rewrite of a
# bounded list (entries older than 15 min are dropped on each append). The UI
# just reads the whole file each poll.
XRUN_FILE = "/tmp/pi-stomp-jackbridge.xruns"
POLL_INTERVAL_S = 2.0
CARRIER_FILE = "/sys/class/net/%s/carrier" % IFACE


class EthernetManager:
    """Polls Ethernet carrier + JackBridge service state on a background thread.

    Mirrors the WifiManager flag-drain pattern: the thread mutates state under
    a lock and flips `_changed`; the handler's main poll loop calls
    `drain_changed()` and notifies the UI on its own thread. xrun stats are
    read on demand (from the menu) rather than cached, since the file is
    bounded and cheap to re-read.
    """

    def __init__(self) -> None:
        self.carrier_up: bool = False
        self.service_active: bool = False
        self._changed: bool = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ethernet-mgr")
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)

    def __del__(self) -> None:
        try:
            self.shutdown()
        except Exception:
            pass

    # ----- background polling -----

    def _run(self) -> None:
        # Prime state immediately so the first UI tick sees real values.
        self._refresh()
        while not self._stop.wait(POLL_INTERVAL_S):
            self._refresh()

    def _refresh(self) -> None:
        carrier = self._read_carrier()
        active = self._read_service_active() if carrier else False
        with self._lock:
            if carrier != self.carrier_up or active != self.service_active:
                self.carrier_up = carrier
                self.service_active = active
                self._changed = True

    def drain_changed(self) -> bool:
        with self._lock:
            c = self._changed
            self._changed = False
            return c

    @staticmethod
    def _read_carrier() -> bool:
        try:
            with open(CARRIER_FILE) as f:
                return f.read().strip() == "1"
        except OSError:
            return False

    @staticmethod
    def _read_service_active() -> bool:
        try:
            return subprocess.call(
                ["systemctl", "is-active", "--quiet", SERVICE]
            ) == 0
        except Exception as e:
            logging.warning("systemctl is-active failed for %s: %s", SERVICE, e)
            return False

    # ----- on-demand reads (called from UI thread when the menu renders) -----

    def read_ipv4(self) -> Optional[str]:
        """Returns "<addr>/<prefix>" for the first IPv4 on the interface, or None."""
        try:
            out = subprocess.check_output(
                ["ip", "-4", "-o", "addr", "show", IFACE], timeout=2
            ).decode()
        except Exception as e:
            logging.debug("ip addr show %s failed: %s", IFACE, e)
            return None
        for line in out.splitlines():
            parts = line.split()
            if "inet" in parts:
                i = parts.index("inet")
                if i + 1 < len(parts):
                    return parts[i + 1]
        return None

    def read_jack_settings(self) -> tuple[Optional[int], Optional[int]]:
        return self._jack_int("jack_samplerate"), self._jack_int("jack_bufsize")

    @staticmethod
    def _jack_int(cmd: str) -> Optional[int]:
        try:
            out = subprocess.check_output([cmd], timeout=2).decode().strip()
            return int(out.split()[0]) if out else None
        except Exception as e:
            logging.debug("%s failed: %s", cmd, e)
            return None

    @staticmethod
    def read_xrun_buckets() -> tuple[int, int, int]:
        """Counts of xruns in the last 1/5/15 minutes from the bounded service file."""
        try:
            with open(XRUN_FILE) as f:
                lines = f.read().splitlines()
        except OSError:
            return (0, 0, 0)
        now = time.time()
        b1 = b5 = b15 = 0
        for line in lines:
            try:
                ts = float(line.strip())
            except ValueError:
                continue
            dt = now - ts
            if dt < 60:
                b1 += 1
            if dt < 300:
                b5 += 1
            if dt < 900:
                b15 += 1
        return b1, b5, b15

    # ----- service control (mutating systemctl calls match the existing
    #       `os.system('sudo systemctl restart jack')` precedent) -----

    def start_service(self) -> None:
        os.system("sudo systemctl start " + SERVICE)

    def stop_service(self) -> None:
        os.system("sudo systemctl stop " + SERVICE)
