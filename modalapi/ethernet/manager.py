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
    """Polls Ethernet carrier + JackBridge state on a background thread.

    Mirrors the WifiManager pattern: all blocking I/O (sysfs, systemctl,
    `ip`, `jack_*`, xrun file) runs on the poll thread and is cached under
    a lock; the UI thread only reads cached values. `_changed` is flipped
    when carrier/service-active flip so the handler's main poll loop can
    notify the UI; field-only changes (IP, sample rate, xruns) are picked
    up by the menu's periodic tick re-render without setting `_changed`.

    Writes (start/stop service) are fire-and-forget via subprocess.Popen
    so the UI thread never blocks on systemctl.
    """

    def __init__(self) -> None:
        self.carrier_up: bool = False
        self.service_active: bool = False
        self._ipv4: Optional[str] = None
        self._sample_rate: Optional[int] = None
        self._period: Optional[int] = None
        self._xruns: tuple[int, int, int] = (0, 0, 0)
        self._changed: bool = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ethernet-mgr")
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)

    # ----- background polling -----

    def _run(self) -> None:
        # Prime state immediately so the first UI tick sees real values.
        self._refresh()
        while not self._stop.wait(POLL_INTERVAL_S):
            self._refresh()

    def _refresh(self) -> None:
        carrier = self._probe_carrier()
        active = self._probe_service_active() if carrier else False
        ipv4 = self._probe_ipv4() if carrier else None
        if active:
            sample_rate = self._probe_jack_int("jack_samplerate")
            period = self._probe_jack_int("jack_bufsize")
            xruns = self._probe_xrun_buckets()
        else:
            sample_rate = period = None
            xruns = (0, 0, 0)
        with self._lock:
            if carrier != self.carrier_up or active != self.service_active:
                self._changed = True
            self.carrier_up = carrier
            self.service_active = active
            self._ipv4 = ipv4
            self._sample_rate = sample_rate
            self._period = period
            self._xruns = xruns

    def drain_changed(self) -> bool:
        with self._lock:
            c = self._changed
            self._changed = False
            return c

    @staticmethod
    def _probe_carrier() -> bool:
        try:
            with open(CARRIER_FILE) as f:
                return f.read().strip() == "1"
        except OSError:
            return False

    @staticmethod
    def _probe_service_active() -> bool:
        try:
            return subprocess.call(
                ["systemctl", "is-active", "--quiet", SERVICE]
            ) == 0
        except Exception as e:
            logging.warning("systemctl is-active failed for %s: %s", SERVICE, e)
            return False

    @staticmethod
    def _probe_ipv4() -> Optional[str]:
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

    @staticmethod
    def _probe_jack_int(cmd: str) -> Optional[int]:
        try:
            out = subprocess.check_output([cmd], timeout=2).decode().strip()
            return int(out.split()[0]) if out else None
        except Exception as e:
            logging.debug("%s failed: %s", cmd, e)
            return None

    @staticmethod
    def _probe_xrun_buckets() -> tuple[int, int, int]:
        # File format (produced by jackbridge-xrun-watcher): up to 15 lines,
        # oldest first, "<epoch_sec_of_minute> <count>". Each bucket covers
        # [ts, ts+60); include it if its END (ts+60) is within the window so a
        # freshly-rolled bucket counts for the 1-min query.
        try:
            with open(XRUN_FILE) as f:
                lines = f.read().splitlines()
        except OSError:
            return (0, 0, 0)
        now = time.time()
        b1 = b5 = b15 = 0
        for line in lines:
            parts = line.split()
            if len(parts) != 2:
                continue
            try:
                ts = float(parts[0])
                count = int(parts[1])
            except ValueError:
                continue
            dt = now - (ts + 60)
            if dt < 60:
                b1 += count
            if dt < 300:
                b5 += count
            if dt < 900:
                b15 += count
        return b1, b5, b15

    # ----- UI-thread reads (return cached values, no I/O) -----

    def read_ipv4(self) -> Optional[str]:
        with self._lock:
            return self._ipv4

    def read_jack_settings(self) -> tuple[Optional[int], Optional[int]]:
        with self._lock:
            return self._sample_rate, self._period

    def read_xrun_buckets(self) -> tuple[int, int, int]:
        with self._lock:
            return self._xruns

    # ----- service control (non-blocking; bg poll picks up the state flip) -----

    def start_service(self) -> None:
        self._spawn_systemctl("start")

    def stop_service(self) -> None:
        self._spawn_systemctl("stop")

    @staticmethod
    def _spawn_systemctl(verb: str) -> None:
        try:
            subprocess.Popen(
                ["sudo", "systemctl", verb, SERVICE],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logging.warning("systemctl %s %s failed to spawn: %s", verb, SERVICE, e)
