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

set -x
set -e

sudo dpkg -i setup/sys/linux-headers-6.1.54-rt15-v8+_6.1.54-rt15-v8+-2_arm64.deb
sudo dpkg -i setup/sys/linux-libc-dev_6.1.54-rt15-v8+-2_arm64.deb
sudo dpkg -i setup/sys/linux-image-6.1.54-rt15-v8+_6.1.54-rt15-v8+-2_arm64.deb

KERN2=6.1.54-rt15-v8+
sudo mkdir -p /boot/firmware/$KERN2/o/
sudo cp -d /usr/lib/linux-image-$KERN2/overlays/* /boot/firmware/$KERN2/o/
sudo cp -dr /usr/lib/linux-image-$KERN2/* /boot/firmware/$KERN2/
sudo cp -d /usr/lib/linux-image-$KERN2/broadcom/* /boot/firmware/$KERN2/
sudo touch /boot/firmware/$KERN2/o/README
sudo mv /boot/vmlinuz-$KERN2 /boot/firmware/$KERN2/
sudo mv /boot/initrd.img-$KERN2 /boot/firmware/$KERN2/
sudo mv /boot/System.map-$KERN2 /boot/firmware/$KERN2/
sudo cp /boot/config-$KERN2 /boot/firmware/$KERN2/
sudo bash -c "cat >> /boot/firmware/config.txt << EOF
[pi4]
kernel=vmlinuz-$KERN2
# initramfs initrd.img-$KERN
os_prefix=$KERN2/
overlay_prefix=o/
arm_64bit=1
[pi4]
EOF"

#Turn off raspi-config service and set performance governor
#sudo raspi-config nonint do_boot_wait 1
#sudo rcconf --off raspi-config
sudo bash -c "echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
