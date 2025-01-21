#!/bin/bash

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