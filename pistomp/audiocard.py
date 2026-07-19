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
import mmap
import os
import re
import subprocess

from pistomp.alsa_pcm import read_hw_params


class Audiocard:
    def __init__(self, cwd):
        self.cwd = cwd
        self.card_index = 0
        self.config_file = "/var/lib/alsa/asound.state"  # global config used by alsamixer, etc.
        self.initial_config_file = None  # use this if common config_file loading fails
        self.initial_config_name = None
        self.card_index = 0
        self.bypass = False

        # Superset of Alsa parameters for all cards (None == not supported)
        # Override in subclass with actual name
        self.CAPTURE_VOLUME = None
        self.DAC_EQ = None
        self.EQ_1 = None
        self.EQ_2 = None
        self.EQ_3 = None
        self.EQ_4 = None
        self.EQ_5 = None
        self.MASTER = None

    def restore(self):
        # If the global config_file either doesn't exist, doesn't contain the name of our audiocard, or fails restore,
        # read initial_config_file (our backup).  This will be the case on first boot after install.
        # Subsequent boots will likely use the global config_file since initial_config_file settings will get
        # appended if a 'alsactl store' operation occurs or the system has a clean shutdown
        conf_files = [self.config_file, self.initial_config_file]
        for fname in conf_files:
            if os.access(fname, os.R_OK) is True:
                try:
                    looking_for = bytes(("state.%s" % self.initial_config_name), "utf-8")
                    f = open(fname)
                    with f as text:
                        s = mmap.mmap(text.fileno(), 0, access=mmap.ACCESS_READ)
                        if s.find(looking_for) != -1:
                            logging.info("restoring audio card settings from: %s" % fname)
                            subprocess.run(["/usr/sbin/alsactl", "-f", fname, "--no-lock", "--no-ucm", "restore"])
                            f.close()
                            # If the file loaded was not the global, then save it so it will be next time
                            if fname is not self.config_file:
                                self.store()
                            break
                    f.close()
                except Exception:
                    logging.error("Failed trying to restore audio card settings from: %s" % fname)

    def store(self):
        # /var/lib/alsa/asound.state is root:root; this process runs as the
        # unprivileged pistomp user, so alsactl needs sudo to lock and write it.
        try:
            subprocess.run(["sudo", "/usr/sbin/alsactl", "-f", self.config_file, "store"], stderr=subprocess.DEVNULL)
            logging.info("audio card settings saved to: %s" % self.config_file)
        except Exception:
            logging.error("Failed trying to store audio card settings to: %s" % self.config_file)

    def get_sample_rate(self) -> int:
        # Raises rather than returning None: we Requires=jack.service, so jackd
        # holds the PCM open whenever we run and a missing rate is a broken invariant
        rate = read_hw_params(self.card_index).get("rate")
        if rate is None:
            raise RuntimeError("no PCM rate for card %d; is jackd holding it?" % self.card_index)
        return int(rate)

    def _amixer_sget(self, param_name):
        cmd = "amixer -c %d -- sget '%s'" % (self.card_index, param_name)
        try:
            output = subprocess.check_output(cmd, shell=True)
        except subprocess.CalledProcessError:
            logging.error("Failed trying to get audio card parameter")
            return ""
        return output.decode()

    def _amixer_sset(self, param_name, value, store):
        # when store is False settings will not be persisted between sessions unless an explicit call
        # to store() is made
        # setting to False is good when you want to set a bunch of things, then store
        cmd = "amixer -c %d -q -- sset '%s' '%s'" % (self.card_index, param_name, value)
        try:
            subprocess.check_output(cmd, shell=True)
        except subprocess.CalledProcessError:
            logging.error("Failed trying to set audio card parameter")
            return False
        if store:
            self.store()
        return True

    def get_bypass_left(self) -> bool:
        return False

    def get_bypass_right(self) -> bool:
        return False

    def set_bypass_left(self, bypass):
        pass

    def set_bypass_right(self, bypass):
        pass

    def set_output_muted(self, muted: bool) -> None:
        if self.MASTER is not None:
            self._amixer_sset(self.MASTER, "mute" if muted else "unmute", store=False)

    #
    # Use the following get and set methods depending on the value type
    #
    def get_volume_parameter(self, param_name):
        # for fader controls with values in dB, returns a float
        if param_name is None:
            return float(0)
        s = self._amixer_sget(param_name)
        pattern = r": (.*)(\d+) \[(\d+%)\] \[(-?\d+\.\d+)dB\]"
        matches = re.search(pattern, s)
        if matches:
            return round(float(matches.group(4)), 1)
        return float(0)

    def get_switch_parameter(self, param_name):
        # for switch/mute type controls, returns a boolean
        if param_name is None:
            return False
        s = self._amixer_sget(param_name)
        pattern = r": (.*) \[(on|off)\]"
        matches = re.search(pattern, s)
        if matches:
            return bool("on" == matches.group(2))
        return False

    def get_enum_parameter(self, param_name):
        # for enum/selection type controls, returns a string
        if param_name is None:
            return None
        s = self._amixer_sget(param_name)
        pattern = r"Item0: '(.+)'"
        matches = re.search(pattern, s)
        if matches:
            return matches.group(1)
        return None

    def set_volume_parameter(self, param_name, value, store=True):
        # value expected to be a number (int or float)
        return self._amixer_sset(param_name, str(value) + "db", store)

    def set_switch_parameter(self, param_name, value, store=True):
        # value expected to be a boolean
        return self._amixer_sset(param_name, "on" if value else "off", store)

    def set_enum_parameter(self, param_name, value, store=True):
        # value expected to be a string (specifically one of the enum choices for the parameter)
        return self._amixer_sset(param_name, str(value), store)
