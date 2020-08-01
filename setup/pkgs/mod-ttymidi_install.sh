#!/bin/bash -e

pushd $(mktemp -d) && git clone https://github.com/moddevices/mod-ttymidi.git
pushd mod-ttymidi
sudo make install
