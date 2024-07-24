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
import threading
import subprocess
import logging

class WifiManager():

    # For now hard wire wifi interface to avoid spending time scrubbing sysfs
    #
    # our hotspot scripts are also hard wired to this name. Long run we could make
    # it a config option or similar... or better plumb the whole thing with a
    # proper network management, but we aren't there. Alternatively, we could
    # monitor for hotplug events via dbus...
    #
    def __init__(self, ifname = 'wlan0'):
        # Grab default wifi interface
        self.iface_name = 'wlan0'
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
            subprocess.check_output(['systemctl', 'is-active', 'wifi-hotspot', '--quiet']).strip().decode('utf-8')
        except:
            return False
        return True

    def _get_wpa_status(self, status):
        try:
            text_out = subprocess.check_output(['wpa_cli', '-i', self.iface_name, 'status']).strip().decode('utf-8')
            for i in text_out.split('\n'):
                if len(i) is 0:
                    continue
                (key, value) = i.split('=')
                if key and value:
                    status[key] = value
        except Exception as e:
            logging.error("WPA CLI fail:" + str(e))

    def _polling_thread(self):
        while not self.stop.wait(5.0):
            new_status = {}
            new_status['wifi_supported'] = supported = self._is_wifi_supported()
            new_status['wifi_connected'] = connected = self._is_wifi_connected()
            new_status['hotspot_active'] = hp_active = self._is_hotspot_active()
            if supported and (connected or hp_active):
                self._get_wpa_status(new_status)
            if new_status != self.last_status:
                logging.debug("Wifi status changed:" + str(new_status))
                self.lock.acquire()
                self.last_status = new_status
                self.changed = True
                self.lock.release()

    # External API
    def poll(self):
        if self.changed:
            logging.debug("wifi poll changed detect !")
            # We don't need to do a deep copy because that dictionnary content
            # is never modified by the Timer thread (the whole dictionnary is
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
            subprocess.check_output(['sudo', 'systemctl', 'enable', 'wifi-hotspot']).strip().decode('utf-8')
            subprocess.check_output(['sudo', 'systemctl', 'start', 'wifi-hotspot']).strip().decode('utf-8')
        except:
            logging.debug('Wifi hotspot enabling failed')

    def disable_hotspot(self):
        try:
            subprocess.check_output(['sudo', 'systemctl', 'stop', 'wifi-hotspot']).strip().decode('utf-8')
            subprocess.check_output(['sudo', 'systemctl', 'disable', 'wifi-hotspot']).strip().decode('utf-8')
        except:
            logging.debug('Wifi hotspot disabling failed')

    def configure_wifi(ssid, password):
        # Disconnect from any connected network
        subprocess.run(['nmcli', 'device', 'disconnect', 'wlan0'], check=True)
    
        # Add a new WiFi connection with the provided SSID and password
        subprocess.run([
            'nmcli', 'device', 'wifi', 'connect', ssid,
            'password', password,
            'ifname', 'wlan0'
        ], check=True)

    def get_wifi_name(self):
        try:
            # Run nmcli command to get connected wifi name
            result = subprocess.run(['nmcli', '-t', '-f', 'NAME', 'connection', 'show', '--active'], capture_output=True, text=True)
            
            # Extract the wifi name from the output
            wifi_name = result.stdout.strip()
        except:
            logging.debug('Failure running nmcli to get wifi name')
