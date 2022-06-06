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

DEFAULT_CONFIG_FILE = "default_config.yml"


def load_default_cfg():
    # Read the default config file - should only need to read once per session
    script_dir = os.path.dirname(os.path.realpath(__file__))
    default_config_file = os.path.join(script_dir, DEFAULT_CONFIG_FILE)
    with open(default_config_file, 'r') as ymlfile:
        cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
        return cfg
