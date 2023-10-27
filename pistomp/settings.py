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

import os
import yaml
import common.util as Util
import shutil

DATA_DIR = '/home/pistomp/data/config'
SETTINGS_FILE = 'settings.yml'
USER = 'pistomp'

# The settings file and this class are for persisting simple settings (name value pairs)
# This is different from the "config" files (eg. default_config.yml) since those files are
# user generated and read-only.  The settings file is meant to be read and written by the
# software, and not intended to be user editable even though values may be set via the LCD.


class Settings:

    def __init__(self):
        self.data = None
        self.file = os.path.join(DATA_DIR, SETTINGS_FILE)
        self.load_settings()

    def load_settings(self):
        try:
            with open(self.file, 'r') as ymlfile:
                self.data = yaml.load(ymlfile, Loader=yaml.SafeLoader)
        except:
            # File can't be opened so let's create an empty dict then calls to set_setting() will save/create the file
            self.data = {}

    def get_setting(self, name):
        if self.data is None:
            self.load_settings()
        if self.data:
            return Util.DICT_GET(self.data, name)
        return None

    def set_setting(self, name, value):
        self.data[name] = value
        # Each set results in a file dump
        with open(self.file, 'w') as ymlfile:
            yaml.dump(self.data, ymlfile)
            shutil.chown(self.file, user=USER, group=USER)
