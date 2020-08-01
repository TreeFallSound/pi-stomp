#!/bin/bash -e

# LILV
pushd $(mktemp -d)
git clone https://github.com/moddevices/lilvlib.git
pushd lilvlib
sudo apt-get update
sed 's/generic/cortex-a53/; s/# sudo apt-get install/sudo apt-get install --yes --force-yes/; s/^debuild/#debuild/; s/# fakeroot/fakeroot/ ' build-python3-lilv.sh > my-build-python3-lilv.sh
chmod +x my-build-python3-lilv.sh
sudo ./my-build-python3-lilv.sh && sudo dpkg -i python3-lilv*_armhf.deb
