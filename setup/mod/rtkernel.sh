#!/bin/bash

set -x
set -e

sudo dpkg -i linux-image-5.15.12-rt25-v8+_5.15.12-1_arm64.deb

KERN=5.15.12-rt25-v8+
sudo mkdir -p /boot/$KERN/o/
sudo cp -d /usr/lib/linux-image-$KERN/overlays/* /boot/$KERN/o/
sudo cp -dr /usr/lib/linux-image-$KERN/* /boot/$KERN/
sudo touch /boot/$KERN/overlays/README
sudo mv /boot/vmlinuz-$KERN /boot/$KERN/
sudo mv /boot/System.map-$KERN /boot/$KERN/
sudo cp /boot/config-$KERN /boot/$KERN/
sudo cat >> /boot/config.txt << EOF

[all]
kernel=vmlinuz-$KERN
# initramfs initrd.img-$KERN
os_prefix=$KERN/
overlay_prefix=o/
[all]
EOF

#Turn off raspi-config service and set performance governor
sudo rcconf --off raspi-config
sudo "echo performance > /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
