#!/bin/bash -e

# Get example pedalboards, copy to pedalboard directory
pushd $(mktemp -d) && git clone https://github.com/TreeFallSound/pi-stomp-pedalboards.git

sudo cp -r pi-stomp-pedalboards/*.pedalboard /usr/local/modep/.pedalboards
