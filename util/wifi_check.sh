#!/bin/bash

LOG="/home/pistomp/wifi_check.log"

iwgetid -r &>/dev/null

if [ $? -eq 0 ]; then
    echo "Wifi is connected." >> "$LOG"
else
    sudo systemctl start wifi-hotspot.service
    echo "Wifi not connected. Starting hotspot." >> "$LOG"
fi