#!/bin/bash

# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

LOG="/var/log/wifi.log"
CURRENTDATE=$( date '+%F_%H:%M:%S' )

iwgetid -r &>/dev/null

if [ $? -eq 0 ]; then
    echo "${CURRENTDATE} Wifi is connected." >> "$LOG"
else
    sudo systemctl restart wifi-hotspot.service
    echo "${CURRENTDATE} Wifi not connected. Starting hotspot." >> "$LOG"
fi
