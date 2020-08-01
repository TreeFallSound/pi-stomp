#!/bin/bash -e

# Install libraries required for build
sudo apt install libcairo2-dev libx11-dev

# Build and install into ~/.lv2
pushd $(mktemp -d) && git clone https://github.com/brummer10/GxPlugins.lv2.git
cd *
git submodule init
git submodule update
make
make install

