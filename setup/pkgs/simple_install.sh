#!/bin/bash -e

# Pyyml
sudo /usr/bin/pip3 install pyyaml

# Midi
sudo /usr/bin/pip3 install python-rtmidi

# Requests
sudo /usr/bin/pip3 install requests

# GPIO
sudo /usr/bin/pip3 install RPi.GPIO

# LCD
sudo /usr/bin/pip3 install adafruit-circuitpython-rgb-display

# MCP3xxx (ADC support)
pushd $(mktemp -d) && curl https://files.pythonhosted.org/packages/57/3a/2d62e66b60619d6f15a2ebf08ad77fcc4196c924e489ec22b66e1977d88b/adafruit-circuitpython-mcp3xxx-1.4.1.tar.gz > mcp.tgz
sudo /usr/bin/pip3 install mcp.tgz
