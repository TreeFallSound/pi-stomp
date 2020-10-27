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
import subprocess


class Audiocard:

    def __init__(self):
        self.card_index = 0
        self.config_file = '/var/lib/alsa/asound.state'  # global config used by alsamixer, etc.
        self.initial_config_file = None  # use this if common config_file loading fails
        self.initial_config_name = None
        self.CAPTURE_VOLUME = 'Capture Volume'
        self.MASTER = 'Master'

    def restore(self):
        # If the global config_file either doesn't exist, doesn't contain the name of our audiocard, or fails restore,
        # read initial_config_file (our backup).  This will be the case on first boot after install.
        # Subsequent boots will likely use the global config_file since initial_config_file settings will get
        # appended if a 'alsactl store' operation occurs or the system has a clean shutdown
        conf_files = [self.config_file, self.initial_config_file]
        for fname in conf_files:
            if os.access(fname, os.R_OK) is True:
                try:
                    looking_for = bytes(("state.%s" % self.initial_config_name), 'utf-8')
                    f = open(fname)
                    with f as text:
                        s = mmap.mmap(text.fileno(), 0, access=mmap.ACCESS_READ)
                        if s.find(looking_for) != -1:
                            subprocess.run(['/usr/sbin/alsactl', '-f', fname, '--no-lock', 'restore'])
                            break
                    f.close()
                except:
                    logging.error("Failed trying to restore audio card settings from: %s" % fname)

    def store(self):
        # This will fail when the top level program is not run as root
        # Unfortunate that setting changes will not be persisted between boots, but not worth getting the mess of
        # dealing with file permissions or sync issues when settings are changed via another program (eg. aslamixer)
        try:
            subprocess.run(['/usr/sbin/alsactl', '-f', self.config_file, 'store'])
        except:
            logging.error("Failed trying to store audio card settings to: %s" % self.config_file)

    def get_parameter(self, param_name):
        val_str = 0
        cmd = "amixer -c %d -- sget %s" % (self.card_index, param_name)
        try:
            output = subprocess.check_output(cmd, shell=True)
        except subprocess.CalledProcessError:
            logging.error("Failed trying to get audio card parameter")
            return 0
        s = output.decode()
        # TODO kinda lame screenscrape here for the last value eg. [0.58db] then strip off the []'s and db
        res = s.rfind('[')
        if res > 0:
            val_str = s[res+1:-4]
        value = float(val_str)
        return value

    def set_parameter(self, param_name, value):
        cmd = "amixer -c %d -q -- sset %s %ddb" % (self.card_index, param_name, value)
        try:
            subprocess.check_output(cmd, shell=True)
        except subprocess.CalledProcessError:
            logging.error("Failed trying to set audio card parameter")
        self.store()


