#!/bin/bash

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

# check the device tree overlay is setup correctly ...
# firstly disable PWM audio
sudo bash -c "sed -i \"s/^\s*dtparam=audio/#dtparam=audio/\" /boot/firmware/config.txt"

# add alsa restore to rc.local
sudo patch -b -N -u /etc/rc.local -i setup/audio/rclocal.diff

# append lines to config.txt
cnt=$(grep -c "dtoverlay=audioinjector-wm8731-audio" /boot/config.txt)
if [[ "$cnt" -eq "0" ]]; then
sudo bash -c "cat >> /boot/firmware/config.txt <<EOF

# enable the sound card (uncomment only one)
#dtoverlay=audioinjector-wm8731-audio
dtoverlay=iqaudio-codec
#dtoverlay=hifiberry-dacplusadc
EOF"
fi

