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


class Audiocard:

    def __init__(self):
        self.card_index = 0
        self.config_file = '/var/lib/alsa/asound.state'
        self.initial_config_file = None  # use this if common config_file loading fails
        self.CAPTURE_VOLUME = 'Capture Volume'
        self.MASTER = 'Master'

    def restore(self):
        # If the global config_file either doesn't exist or fails restore, read the initial_config_file
        # This will be the case on first boot after install
        conf_files = [self.config_file, self.initial_config_file]
        for f in conf_files:
            if os.access(f, os.R_OK) is True:
                try:
                    subprocess.run(['/usr/sbin/alsactl', '-f', f, '--no-lock', 'restore'])
                    break
                except:  #subprocess.CalledProcessError:
                    logging.error("Failed trying to restore audio card settings from: %s" % f)

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


