#!/bin/bash -e

set +e

sudo sed -i 's/console=serial0,115200//' /boot/cmdline.txt

sudo patch -b -N -u /boot/config.txt -i setup/sys/config.txt.diff


exit 0
