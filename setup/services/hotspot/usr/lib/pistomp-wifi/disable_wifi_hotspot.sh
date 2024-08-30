#!/bin/bash

status=$(systemctl is-system-running)
if [ "$status" == "stopping" ]; then
	exit
fi

# Unblock Wi-Fi
rfkill unblock wifi

# Stop the hotspot and related services
nmcli connection down Hotspot
nmcli connection delete Hotspot

# If hostapd and dnsmasq are running outside of NM, stop them
sudo systemctl stop hostapd
sudo systemctl stop dnsmasq
sudo systemctl disable hostapd
sudo systemctl disable dnsmasq

# Reset IP forwarding and iptables (only needed if custom rules were added)
echo 0 | sudo tee /proc/sys/net/ipv4/ip_forward
sudo iptables -t nat -F
sudo iptables -F

# Restart the NetworkManager to reset the interface (this seems to cause issues when bringing wlan0 back up)
#sudo systemctl restart NetworkManager

# Restart Avahi Daemon if needed
sudo systemctl restart avahi-daemon

# Connect to a Wi-Fi network using NetworkManager
nmcli device up wlan0

# Optional: Connect to a specific Wi-Fi network
# nmcli device wifi connect "YourSSID" password "YourPassword"
