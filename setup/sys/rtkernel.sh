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

sudo dpkg -i setup/sys/linux-image-5.15.65-rt49-v8+_5.15.65-rt49-v8+-2_arm64.deb
sudo dpkg -i setup/sys/linux-headers-5.15.65-rt49-v8+_5.15.65-rt49-v8+-2_arm64.deb
sudo dpkg -i setup/sys/linux-libc-dev_5.15.65-rt49-v8+-2_arm64.deb

KERN=5.15.65-rt49-v8+
sudo mkdir -p /boot/$KERN/o/
sudo cp -d /usr/lib/linux-image-$KERN/overlays/* /boot/$KERN/o/
sudo cp -dr /usr/lib/linux-image-$KERN/* /boot/$KERN/
sudo cp -d /usr/lib/linux-image-$KERN/broadcom/* /boot/$KERN/
sudo touch /boot/$KERN/o/README
sudo mv /boot/vmlinuz-$KERN /boot/$KERN/
sudo mv /boot/initrd.img-$KERN /boot/$KERN/
sudo mv /boot/System.map-$KERN /boot/$KERN/
sudo cp /boot/config-$KERN /boot/$KERN/
sudo bash -c "cat >> /boot/config.txt << EOF
[all]
kernel=vmlinuz-$KERN
# initramfs initrd.img-$KERN
os_prefix=$KERN/
overlay_prefix=o/
arm_64bit=1
[all]
EOF"

#Turn off raspi-config service and set performance governor
sudo rcconf --off raspi-config
sudo bash -c "echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
