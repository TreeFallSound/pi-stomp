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

deb_file=audio.injector.scripts_0.1-1_all.deb
wget https://github.com/Audio-Injector/stereo-and-zero/raw/master/${deb_file}

sudo dpkg -i ${deb_file} 

rm -f ${deb_file}

# Modify audioInjector-setup.sh to not run rpi-update
sudo sed -i 's/sudo rpi-update/#sudo rpi-update/' /usr/bin/audioInjector-setup.sh

# Execute setup
/usr/bin/audioInjector-setup.sh

# Change jack.service to use the audioinjector card (this is only for non-patchbox based modep installs)
#sudo sed -i -e 's/hw:pisound/hw:audioinjectorpi/' -e 's/-n 2/-n 3/' /usr/lib/systemd/system/jack.service

# Change amixer settings
sudo cp setup/audio/asound.state.RCA.thru.test /usr/share/doc/audioInjector/asound.state.RCA.thru.test
