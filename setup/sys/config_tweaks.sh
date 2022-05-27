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

set +e

sudo sed -i 's/console=serial0,115200//' /boot/cmdline.txt

# Remove devices not needed for audio
sudo bash -c "sed -i \"s/^\s*hdmi_force_hotplug=/#hdmi_force_hotplug=/\" /boot/config.txt"
sudo bash -c "sed -i \"s/^\s*camera_auto_detect=/#camera_auto_detect=/\" /boot/config.txt"
sudo bash -c "sed -i \"s/^\s*display_auto_detect=/#display_auto_detect=/\" /boot/config.txt"
sudo bash -c "sed -i \"s/^\s*dtoverlay=vc4-kms-v3d/#dtoverlay=vc4-kms-v3d/\" /boot/config.txt"

# append lines to config.txt
cnt=$(grep -c "dtoverlay=pi3-disable-bt" /boot/config.txt)
if [[ "$cnt" -eq "0" ]]; then
sudo bash -c "cat >> /boot/config.txt <<EOF

# pi-stomp additions to allow DIN Midi, disables bluetooth however
enable_uart=1
dtoverlay=pi3-disable-bt
dtoverlay=pi3-miniuart-bt
dtoverlay=midi-uart0
EOF"
fi

exit 0
