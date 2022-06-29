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

wget -P /home/pistomp/pi-stomp/setup/sys https://github.com/kdoren/linux/releases/download/rpi_5.15.40/linux-image-5.15.40-llat-v8+_5.15.40-1_arm64.deb
sudo dpkg -i setup/sys/linux-image-5.15.40-llat-v8+_5.15.40-1_arm64.deb

KERN=5.15.40-llat-v8+
sudo mkdir -p /boot/llat/o/
sudo cp -d /usr/lib/linux-image-$KERN/overlays/* /boot/llat/o/
sudo cp -dr /usr/lib/linux-image-$KERN/* /boot/llat/
sudo cp -d /usr/lib/linux-image-$KERN/broadcom/* /boot/llat/
sudo touch /boot/llat/o/README
sudo mv /boot/vmlinuz-$KERN /boot/llat/
sudo mv /boot/initrd.img-$KERN /boot/llat/
sudo mv /boot/System.map-$KERN /boot/llat/
sudo cp /boot/config-$KERN /boot/llat/
sudo bash -c "cat >> /boot/config.txt << EOF
[all]
kernel=vmlinuz-$KERN
# initramfs initrd.img-$KERN
os_prefix=llat/
overlay_prefix=o/
arm_64bit=1
[all]
EOF"

#Turn off raspi-config service and set performance governor
sudo rcconf --off raspi-config
sudo bash -c "echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
