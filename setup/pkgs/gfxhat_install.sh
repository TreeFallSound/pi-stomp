#!/bin/bash -e

# GFXHat LCD
pushd $(mktemp -d)
curl -k https://get.pimoroni.com/gfxhat > gfxhat.sh
sed -i 's/pip2support="yes"/pip2support="no"/' gfxhat.sh
chmod a+x gfxhat.sh
./gfxhat.sh -y

