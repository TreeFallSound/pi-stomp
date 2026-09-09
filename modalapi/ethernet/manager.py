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

"""Ethernet (wired) status — a read-only view of the pi JackBridge slave.

The Mac drives the bridge lifecycle: this class only reports what the unit
does. There is no start or stop method here — that path caused the
duplicate-netadapter bug.

`jackbridge-pi-status` supplies the data (pistomp-companion installs it).
The helper only reads: systemd state, the jack_lsp graph, the IP route,
xrun counts, and netadapter link restarts. Like WifiManager, a background thread does all blocking
I/O and caches the result. The UI thread reads the cache through the
read_* methods.
"""

import logging
import os
import subprocess
import threading
from functools import cached_property
from typing import Optional

from common.util import TEARDOWN_JOIN_S
from pistomp.alsa_pcm import read_hw_params

# Source: pistomp-companion jackbridge/pi/bin/. It reaches the pi only
# through pi-gen-pistomp's `jackbridge` deb — add it to that deb's
# debian/rules install list, which is a separate manifest from
# companion's own install.sh.
STATUS_BIN = "/usr/local/libexec/jackbridge/jackbridge-pi-status"
POLL_INTERVAL_S = 2.0


def _int(s: Optional[str]) -> int:
    """Parse an int from status output. Return 0 for None, empty, or bad text."""
    if not s:
        return 0
    try:
        return int(s)
    except ValueError:
        return 0


class EthernetManager:
    """Poll the Ethernet carrier and the JackBridge status on a background thread.

    Read-only. `_changed` is set when the carrier, the service-active state
    or the link-resyncing state changes, so the handler poll loop can refresh the UI. Field
    changes (IP, sample rate, xruns, port counts) appear on the next
    render without `_changed`.
    """

    @cached_property
    def iface(self) -> str:
        """First wired (non-loopback, non-wireless) interface found in sysfs."""
        try:
            for name in sorted(os.listdir("/sys/class/net")):
                if name == "lo":
                    continue
                if os.path.exists(f"/sys/class/net/{name}/wireless"):
                    continue
                return name
        except OSError:
            pass
        return "eth0"

    def __init__(self) -> None:
        self.carrier_up: bool = False
        self.service_active: bool = False
        self._netadapters: int = 0
        self._ports_wired: int = 0
        self._route: str = ""
        self._link_resyncing: bool = False
        self._net_restarts: int = 0
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
        self._thread.join(timeout=TEARDOWN_JOIN_S)

    # ----- background polling -----

    def _run(self) -> None:
        # Prime state immediately so the first UI tick sees real values.
        self._refresh()
        while not self._stop.wait(POLL_INTERVAL_S):
            self._refresh()

    def _refresh(self) -> None:
        carrier = self._probe_carrier()
        status = self._read_pi_status() if carrier else {}

        active = status.get("service") == "active"
        netadapters = _int(status.get("netadapters"))
        ports_wired = _int(status.get("ports_wired"))
        route = status.get("route", "") or ""
        link_resyncing = status.get("link") == "resyncing"
        net_restarts = _int(status.get("net_restarts"))
        xruns = (
            _int(status.get("xruns_1m")),
            _int(status.get("xruns_5m")),
            _int(status.get("xruns_15m")),
        )
        ipv4 = self._probe_ipv4() if carrier else None

        if active:
            # One /proc read. jack_samplerate and jack_bufsize each fork and
            # join the RT graph to read what hw_params already holds.
            params = read_hw_params()
            sample_rate = int(params["rate"]) if "rate" in params else None
            period = int(params["period_size"]) if "period_size" in params else None
        else:
            sample_rate = period = None

        with self._lock:
            if carrier != self.carrier_up or active != self.service_active or link_resyncing != self._link_resyncing:
                self._changed = True
            self.carrier_up = carrier
            self.service_active = active
            self._netadapters = netadapters
            self._ports_wired = ports_wired
            self._route = route
            self._link_resyncing = link_resyncing
            self._net_restarts = net_restarts
            self._ipv4 = ipv4
            self._sample_rate = sample_rate
            self._period = period
            self._xruns = xruns

    def drain_changed(self) -> bool:
        with self._lock:
            c = self._changed
            self._changed = False
            return c

    def _probe_carrier(self) -> bool:
        try:
            with open(f"/sys/class/net/{self.iface}/carrier") as f:
                return f.read().strip() == "1"
        except OSError:
            return False

    @staticmethod
    def _read_pi_status() -> dict[str, str]:
        """Run jackbridge-pi-status and parse its key=value lines.

        The helper only reads and always exits 0. Any error gives an empty
        dict, which the callers treat as zeros.
        """
        try:
            out = subprocess.check_output(
                [STATUS_BIN],
                text=True,
                timeout=3,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logging.debug("jackbridge-pi-status failed: %s", e)
            return {}

        status: dict[str, str] = {}
        for line in out.splitlines():
            key, sep, val = line.partition("=")
            if sep:
                status[key] = val
        return status

    def _probe_ipv4(self) -> Optional[str]:
        try:
            out = subprocess.check_output(["ip", "-4", "-o", "addr", "show", self.iface], timeout=2).decode()
        except Exception as e:
            logging.debug("ip addr show %s failed: %s", self.iface, e)
            return None
        for line in out.splitlines():
            parts = line.split()
            if "inet" in parts:
                i = parts.index("inet")
                if i + 1 < len(parts):
                    return parts[i + 1]
        return None

    # ----- UI-thread reads (cached values; no I/O) -----

    def read_ipv4(self) -> Optional[str]:
        with self._lock:
            return self._ipv4

    def read_jack_settings(self) -> tuple[Optional[int], Optional[int]]:
        with self._lock:
            return self._sample_rate, self._period

    def read_xrun_buckets(self) -> tuple[int, int, int]:
        with self._lock:
            return self._xruns

    def read_link_health(self) -> tuple[bool, int]:
        """(resyncing, restarts). Cached; read from the UI thread."""
        with self._lock:
            return self._link_resyncing, self._net_restarts

    def read_netadapter_health(self) -> tuple[int, int, str]:
        """(netadapters, ports_wired, route). Cached; read from the UI thread.

        `netadapters > 1` means the duplicate-slave bug. An empty route, or
        a route on a wireless interface, means the Wi-Fi-escape case.
        """
        with self._lock:
            return self._netadapters, self._ports_wired, self._route
