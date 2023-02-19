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

DEST=/usr/share/mod/pedalboards/

# First create the default factory pedalboards folder
sudo mkdir -p /usr/share/mod/pedalboards/
# Get example pedalboards, copy to pedalboard directory
pushd $(mktemp -d) && git clone https://github.com/TreeFallSound/pi-stomp-pedalboards.git

sudo cp -rT pi-stomp-pedalboards $DEST

sudo chown -R pistomp $DEST
sudo chgrp -R pistomp $DEST
