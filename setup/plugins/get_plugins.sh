#!/bin/bash

set -x

wget https://www.treefallsound.com/downloads/lv2plugins.tar.gz
tar -zxf lv2plugins.tar.gz /home/pistomp
rm lv2plugins.tar.gz
