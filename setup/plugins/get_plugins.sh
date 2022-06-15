#!/bin/bash

set -x

wget https://www.treefallsound.com/downloads/lv2plugins.tar.gz
tar -zxf lv2plugins.tar.gz $HOME
rm lv2plugins.tar.gz
