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

# LILV
pushd $(mktemp -d)
git clone https://github.com/moddevices/lilvlib.git
pushd lilvlib
sudo apt-get update
sed 's/generic/cortex-a53/; s/# sudo apt-get install/sudo apt-get install --yes --force-yes/; s/^debuild/#debuild/; s/# fakeroot/fakeroot/ ' build-python3-lilv.sh > my-build-python3-lilv.sh
chmod +x my-build-python3-lilv.sh
sudo ./my-build-python3-lilv.sh && sudo dpkg -i python3-lilv*_armhf.deb
