#!/bin/bash -e

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

sudo cp setup/services/*.service /usr/lib/systemd/system/
sudo ln -sf /usr/lib/systemd/system/mod-ala-pi-stomp.service /etc/systemd/system/multi-user.target.wants

if [ x"$has_ttymidi" == x"true" ]; then
    echo "Enabling ttymidi service"
    sudo ln -sf /usr/lib/systemd/system/ttymidi.service /etc/systemd/system/multi-user.target.wants
fi

#Copy WiFi hotspot files
sudo cp setup/services/hotspot/etc/default/hostapd.pistomp /etc/default
sudo cp setup/services/hotspot/etc/dnsmasq.d/wifi-hotspot.conf /etc/dnsmasq.d
sudo cp setup/services/hotspot/etc/hostapd/hostapd.conf /etc/hostapd
sudo cp -R setup/services/hotspot/usr/lib/pistomp-wifi /usr/lib
sudo cp setup/services/hotspot/usr/lib/systemd/system/wifi-hotspot.service /usr/lib/systemd/system
sudo chown -R pistomp:pistomp /usr/lib/pistomp-wifi
sudo chmod +x -R /usr/lib/pistomp-wifi

# USB automounter
sudo dpkg -i setup/services/usbmount.deb

# Disable wait for network on boot
sudo raspi-config nonint do_boot_wait 1

# Copy wifi_check script
sudo cp setup/services/wifi_check.sh /etc/wpa_supplicant/

# Copy wlan0.conf to prevent wifi power save mode
sudo cp wlan0.conf /etc/network/interfaces.d/
