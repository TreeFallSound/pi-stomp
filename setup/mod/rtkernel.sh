#!/bin/bash

set -x
set -e

sudo apt install ./linux-image-5.15.12-rt25-v8+_5.15.12-1_arm64.deb

KERN=5.15.12-rt25-v8+
sudo mkdir -p /boot/rtk/o/
sudo cp -d /usr/lib/linux-image-$KERN/overlays/* /boot/rtk/o/
sudo cp -dr /usr/lib/linux-image-$KERN/* /boot/rtk/
sudo cp -d /usr/lib/linux-image-$KERN/broadcom/* /boot/rtk/
sudo touch /boot/rtk/o/README
sudo mv /boot/vmlinuz-$KERN /boot/rtk/
sudo mv /boot/initrd.img-$KERN /boot/rtk/
sudo mv /boot/System.map-$KERN /boot/rtk/
sudo cp /boot/config-$KERN /boot/rtk/
sudo bash -c "cat >> /boot/config.txt << EOF
[all]
kernel=vmlinuz-$KERN
# initramfs initrd.img-$KERN
os_prefix=rtk/
overlay_prefix=o/
arm_64bit=1
[all]
EOF"

#Turn off raspi-config service and set performance governor
sudo rcconf --off raspi-config
sudo bash -c "echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
