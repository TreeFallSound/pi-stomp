#!/bin/bash

# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

Sudo apt install -y lockfile-progs

mkdir -p $HOME/data/config
mkdir -p "$HOME/data/user-files/Aida DSP Models"

ln -s $HOME/data/.pedalboards /home/pistomp/.pedalboards
ln -s $HOME/.lv2 /home/pistomp/data/.lv2

#move default config files to data dir
cp $HOME/pi-stomp/setup/config_templates/default_config.yml $HOME/data/config

#USB automounter
sudo dpkg -i /home/pistomp/pi-stomp/setup/mod/usbmount.deb