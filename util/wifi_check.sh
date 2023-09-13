#!/bin/bash

LOG="/home/pistomp/wifi_check.log"

iwgetid -r &>/dev/null

if [ $? -eq 0 ]; then
    sudo systemctl disable wifi-hotspot.service
    echo "Wifi is connected." >> "$LOG"
else
    sudo systemctl enable wifi-hotspot.service
    sudo systemctl start wifi-hotspot.service
    echo "Wifi not connected. Starting hotspot." >> "$LOG"
fi