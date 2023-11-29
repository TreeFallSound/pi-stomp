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

# Dependencies
if (which python3 > /dev/null); then true; else
  echo "python3 not found, please install it"
  exit
fi

if (which pip3 > /dev/null); then true; else
  echo "pip3 not found, please install it"
  exit
fi

sudo pip3 install python-config

sudo apt-get -y install liblilv-dev lv2-dev libserd-dev libsord-dev libsratom-dev

# Get it
pushd $(mktemp -d)
wget http://download.drobilla.net/lilv-0.24.12.tar.bz2
tar xvf lilv-0.24.12.tar.bz2
pushd lilv-0.24.12

# configure, build, install
python3 ./waf configure --prefix=/usr/local  --static --static-progs --no-shared --no-utils --no-bash-completion --pythondir=/usr/local/lib/python3.11/dist-packages
python3 ./waf build
sudo python3 ./waf install
