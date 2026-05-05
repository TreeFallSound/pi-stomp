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
#
# Parts of this file borrowed from patchbox-cli
#
# Copyright (C) 2017  Vilniaus Blokas UAB, https://blokas.io/pisound

import os
import re
import threading
import subprocess
import logging


def parse_nmcli_error(stderr):
    """Map a chunk of nmcli stderr to a short user-facing reason."""
    if stderr is None:
        return "unknown error"
    text = stderr.decode('utf-8', errors='replace') if isinstance(stderr, (bytes, bytearray)) else str(stderr)
    lower = text.lower()
    if 'secrets were required' in lower or '802-11-wireless-security.psk' in lower or '(7)' in lower:
        return "auth failed (wrong password)"
    if 'no network with ssid' in lower or 'no suitable' in lower or 'ssid not found' in lower:
        return "network not found"
    if 'ip-config-unavailable' in lower or 'dhcp' in lower:
        return "couldn't get an IP (DHCP timeout)"
    if 'timeout' in lower or 'timed out' in lower:
        return "timed out"
    if 'not authorized' in lower or 'permission denied' in lower:
        return "permission denied"
    # Fall back to first non-empty line, truncated.
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:80]
    return "unknown error"


def _split_terse(line):
    """Split an nmcli -t terse line, honouring backslash-escaped colons."""
    return [p.replace('\\:', ':') for p in re.split(r'(?<!\\):', line)]


class WifiManager():

    # For now hard wire wifi interface to avoid spending time scrubbing sysfs
    #
    # our hotspot scripts are also hard wired to this name. Long run we could make
    # it a config option or similar... or better plumb the whole thing with a
    # proper network management, but we aren't there. Alternatively, we could
    # monitor for hotplug events via dbus...
    #
    HOTSPOT_PROFILE = 'pistomp-hotspot'

    def __init__(self, ifname = 'wlan0'):
        # Grab default wifi interface
        self.iface_name = ifname
        self.ssid = None
        self.psk = None
        self.lock = threading.Lock()
        self.last_status = {}
        self.changed = False
        self.stop = threading.Event()
        self.wireless_supported = False
        self.wireless_file = os.path.join(os.sep, 'sys', 'class', 'net', self.iface_name, 'wireless')
        self.operstate_file = os.path.join(os.sep, 'sys', 'class', 'net', self.iface_name, 'operstate')
        self.thread = threading.Thread(target=self._polling_thread, daemon=True).start()

    def __del__(self):
        logging.info("Wifi monitor cleanup")
        self.stop.set()
        self.thread.join()

    def _is_wifi_supported(self):
        # Once we know it's supported, no need to check the file again
        if self.wireless_supported:
            return True
        self.wireless_supported = os.path.exists(self.wireless_file)
        return self.wireless_supported
    
    def _is_wifi_connected(self):
        try:
            with open(self.operstate_file) as f:
                line = f.readline()
                f.close()
                return line.startswith('up')
        except Exception as e:
            return False

    def _is_hotspot_active(self):
        try:
            result = subprocess.run(['systemctl', 'is-active', 'wifi-hotspot'], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
            if result.stdout.strip() == 'active':
                return True
            else:
                return False
        except:
            return False
        return True

    def _get_wpa_status(self, status):
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS,802-11-WIRELESS.SSID',
                 'device', 'show', self.iface_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        # Map nmcli fields to wpa_cli-like keys for compatibility
                        key = key.strip().replace('GENERAL.', '').replace('802-11-WIRELESS.', '').replace('.', '_').lower()
                        status[key] = value.strip()
        except Exception as e:
            logging.error("NetworkManager status fail:" + str(e))

    def _polling_thread(self):
        while True:
            new_status = {}
            new_status['wifi_supported'] = supported = self._is_wifi_supported()
            new_status['wifi_connected'] = connected = self._is_wifi_connected()
            new_status['hotspot_active'] = hp_active = self._is_hotspot_active()
            if supported and (connected or hp_active):
                self._get_wpa_status(new_status)
            if new_status != self.last_status:
                logging.debug("Wifi status changed:" + str(new_status))
                creds=()
                if supported and connected:
                    active_conn = new_status.get('connection')
                    if active_conn:
                        creds = self._acquire_creds(active_conn)

                self.lock.acquire()
                if supported and connected and creds and len(creds)==2:
                    self.ssid = creds[0]
                    self.psk = creds[1]
                self.last_status = new_status
                self.changed = True
                self.lock.release()

            # loop wait
            if self.stop.wait(5.0):
                break

    # External API
    def poll(self):
        if self.changed:
            logging.debug("wifi poll changed detect !")
            # We don't need to do a deep copy because that dictionary content
            # is never modified by the Timer thread (the whole dictionary is
            # replaced)
            #
            # Note: Use context manager to use a non-blocking lock safely vs. ctrl-C
            with self.lock:
                update = self.last_status
                self.changed = False
            return update
        return None

    def enable_hotspot(self):
        try:
            subprocess.check_output(['sudo', 'systemctl', 'enable', '--now', 'wifi-hotspot']).strip().decode('utf-8')
        except:
            logging.debug('Wifi hotspot enabling failed')

    def disable_hotspot(self):
        try:
            subprocess.check_output(['sudo', 'systemctl', 'disable', '--now', 'wifi-hotspot']).strip().decode('utf-8')
        except:
            logging.debug('Wifi hotspot disabling failed')

    def list_connections(self):
        """Return list of dicts {name, ssid, timestamp} for all wifi profiles, excluding the hotspot.

        timestamp is the unix-seconds of last successful activation (int, 0 if never)."""
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'NAME,TYPE,TIMESTAMP,802-11-WIRELESS.SSID', 'connection', 'show'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            connections = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                parts = _split_terse(line)
                if len(parts) >= 2 and parts[1] == '802-11-wireless':
                    name = parts[0]
                    if name == self.HOTSPOT_PROFILE:
                        continue
                    try:
                        timestamp = int(parts[2]) if len(parts) > 2 and parts[2] else 0
                    except ValueError:
                        timestamp = 0
                    ssid = parts[3] if len(parts) > 3 and parts[3] else name
                    connections.append({'name': name, 'ssid': ssid, 'timestamp': timestamp})
            return connections
        except Exception as e:
            logging.error("Failed to list wifi connections: " + str(e))
            return []

    def scan_networks(self):
        """Return a list of nearby networks as {ssid, signal, security, in_use} dicts.

        Deduplicated by SSID (strongest signal wins), sorted by signal desc, hidden SSIDs filtered."""
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'IN-USE,SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list',
                 '--rescan', 'auto', 'ifname', self.iface_name],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15
            )
        except Exception as e:
            logging.error("wifi scan failed: " + str(e))
            return []

        best = {}
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = _split_terse(line)
            if len(parts) < 4:
                continue
            in_use = parts[0] == '*'
            ssid = parts[1]
            if not ssid:
                continue  # hidden network
            try:
                signal = int(parts[2])
            except ValueError:
                signal = 0
            security = parts[3]
            existing = best.get(ssid)
            if existing is None or signal > existing['signal']:
                best[ssid] = {'ssid': ssid, 'signal': signal,
                              'security': security, 'in_use': in_use}
            elif in_use:
                existing['in_use'] = True
        return sorted(best.values(), key=lambda n: n['signal'], reverse=True)

    def _resolve_unique_name(self, desired, exclude=None):
        """Pick a profile name based on `desired`, suffixing (2)/(3)/... if it collides.

        `exclude` is the existing name of a profile being modified (so it doesn't collide with itself)."""
        existing = {c['name'] for c in self.list_connections()}
        if exclude is not None:
            existing.discard(exclude)
        name = desired
        counter = 2
        while name in existing:
            name = '%s (%d)' % (desired, counter)
            counter += 1
        return name

    def add_connection(self, ssid, psk):
        """Add a new wifi profile. Profile name is the SSID, suffixed if a duplicate exists."""
        name = self._resolve_unique_name(ssid)
        try:
            subprocess.check_output([
                'sudo', 'nmcli', 'connection', 'add',
                'type', 'wifi', 'ifname', self.iface_name,
                'con-name', name,
                'ssid', ssid,
                'wifi-sec.key-mgmt', 'wpa-psk',
                'wifi-sec.psk', psk,
                'connection.autoconnect', 'yes'
            ], stderr=subprocess.STDOUT)
            return None
        except subprocess.CalledProcessError as exc:
            return exc.output

    def delete_connection(self, name):
        """Delete a wifi profile by its NM connection name."""
        try:
            subprocess.check_output(
                ['sudo', 'nmcli', 'connection', 'delete', name],
                stderr=subprocess.STDOUT
            )
            return None
        except subprocess.CalledProcessError as exc:
            return exc.output

    def configure_wifi(self, name, ssid, password):
        """Update the SSID and PSK for an existing wifi profile.

        Auto-syncs connection.id to the new SSID (with collision suffix), so the display
        label can never drift from the SSID."""
        new_name = self._resolve_unique_name(ssid, exclude=name)
        try:
            subprocess.check_output([
                'sudo', 'nmcli', 'connection', 'modify', name,
                'connection.id', new_name,
                '802-11-wireless.ssid', ssid,
                '802-11-wireless-security.psk', password
            ], stderr=subprocess.STDOUT)
            return None
        except subprocess.CalledProcessError as exc:
            return exc.output

    def connect_scanned(self, ssid, psk=None):
        """Join a network discovered via scan. Creates a profile and activates it atomically.

        On failure nmcli cleans up the partial profile, so this doubles as a credential test."""
        cmd = ['sudo', 'nmcli', 'dev', 'wifi', 'connect', ssid, 'ifname', self.iface_name]
        if psk:
            cmd += ['password', psk]
        try:
            subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=45)
            return None
        except subprocess.CalledProcessError as exc:
            return exc.output
        except subprocess.TimeoutExpired:
            return b'connection timed out'

    def connect_saved(self, name):
        """Activate an existing saved profile."""
        try:
            subprocess.check_output(
                ['sudo', 'nmcli', 'connection', 'up', name],
                stderr=subprocess.STDOUT, timeout=45
            )
            return None
        except subprocess.CalledProcessError as exc:
            return exc.output
        except subprocess.TimeoutExpired:
            return b'connection timed out'

    def replace_psk(self, name, psk):
        """Update the PSK on a saved profile and validate by activating it.

        On failure the previous PSK is restored so the saved profile keeps working."""
        old_psk = self.get_psk_for(name)
        try:
            subprocess.check_output(
                ['sudo', 'nmcli', 'connection', 'modify', name,
                 '802-11-wireless-security.psk', psk],
                stderr=subprocess.STDOUT
            )
        except subprocess.CalledProcessError as exc:
            return exc.output

        err = self.connect_saved(name)
        if err is not None and old_psk is not None:
            try:
                subprocess.check_output(
                    ['sudo', 'nmcli', 'connection', 'modify', name,
                     '802-11-wireless-security.psk', old_psk],
                    stderr=subprocess.STDOUT
                )
                logging.info("rolled back PSK on %s after failed connect" % name)
            except subprocess.CalledProcessError as rollback_exc:
                logging.error("PSK rollback failed: " + str(rollback_exc.output))
        return err

    def get_psk_for(self, name):
        """Fetch the stored PSK for a specific wifi profile."""
        try:
            result = subprocess.run(
                ['sudo', 'nmcli', '-s', '-g', '802-11-wireless-security.psk', 'connection', 'show', name],
                stdout=subprocess.PIPE, text=True
            )
            return result.stdout.strip() or None
        except Exception:
            return None

    def _acquire_creds(self, connection_name):
        try:
            result = subprocess.run(
                ['sudo', 'nmcli', '-s', '-g', '802-11-wireless.ssid,802-11-wireless-security.psk', 'connection',
                 'show', connection_name],
                stdout=subprocess.PIPE,
                text=True
            )
            fields = result.stdout.split('\n')
            if len(fields) == 3:
                return fields[:2]
        except:
            logging.debug('Failure running nmcli to get wifi name')

    def get_ssid(self):
        return self.ssid

    def get_psk(self):
        return self.psk
