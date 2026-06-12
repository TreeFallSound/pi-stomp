#!/bin/bash

# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

# Temporary file for EEPROM configuration
TEMP_CONFIG="/tmp/eeprom_config.txt"

# Extract the current EEPROM configuration
sudo rpi-eeprom-config > "$TEMP_CONFIG"

# Update the configuration
if grep -q "^POWER_OFF_ON_HALT=" "$TEMP_CONFIG"; then
    # Update the existing line
    sudo sed -i 's/^POWER_OFF_ON_HALT=.*/POWER_OFF_ON_HALT=1/' "$TEMP_CONFIG"
else
    # Add the setting if it doesn't exist
    sudo echo "POWER_OFF_ON_HALT=1" >> "$TEMP_CONFIG"
fi

# Write the updated configuration back
sudo rpi-eeprom-config --apply "$TEMP_CONFIG"

# Clean up
sudo rm "$TEMP_CONFIG"
