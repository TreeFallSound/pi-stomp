#!/bin/bash -e

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

# pip3
if (which pip3 > /dev/null); then true; else
  sudo apt-get install --fix-broken --fix-missing -y
  sudo apt-get install -y python3-pip
fi

# Pyyml
sudo /usr/bin/pip3 install pyyaml
sudo /usr/bin/pip3 install jsonschema

# For diagnostic test mode
sudo /usr/bin/pip3 install pyalsaaudio

# Midi
sudo /usr/bin/pip3 install python-rtmidi

# Requests
sudo /usr/bin/pip3 install requests

# GPIO
sudo /usr/bin/pip3 install RPi.GPIO

#GFXHat
sudo /usr/bin/pip3 install gfxhat

# LEDstring
sudo /usr/bin/pip3 install matplotlib rpi_ws281x adafruit-circuitpython-neopixel

# LCD
sudo /usr/bin/pip3 install adafruit-circuitpython-rgb-display
sudo apt install -y python3-numpy

# MCP3xxx (ADC support)
pushd $(mktemp -d) && curl https://files.pythonhosted.org/packages/57/3a/2d62e66b60619d6f15a2ebf08ad77fcc4196c924e489ec22b66e1977d88b/adafruit-circuitpython-mcp3xxx-1.4.1.tar.gz > mcp.tgz
sudo /usr/bin/pip3 install mcp.tgz
