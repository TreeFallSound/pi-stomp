#!/bin/bash

SSID='pistomp'  #TODO don't hardcode
PSK='pistompwifi'

# Unblock Wi-Fi
rfkill unblock wifi

# Optional: Set wlan0 as unmanaged by NetworkManager temporarily
# (This step may not be necessary depending on your setup)
#nmcli dev set wlan0 managed no

# Add and configure the hotspot connection
nmcli connection add type wifi ifname wlan0 con-name Hotspot autoconnect no ssid ${SSID}
nmcli connection modify Hotspot 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared
nmcli connection modify Hotspot wifi-sec.key-mgmt wpa-psk
nmcli connection modify Hotspot wifi-sec.psk ${PSK}
nmcli connection modify Hotspot ipv4.addresses 172.24.1.1/24
nmcli connection modify Hotspot ipv4.gateway 172.24.1.1
#nmcli connection modify Hotspot ipv4.dns 8.8.8.8

# Optional: If you need to apply custom iptables rules (shouldn't be needed due to 'shared' setting)
#sudo iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
#sudo iptables -A FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT
#sudo iptables -A FORWARD -i wlan0 -o eth0 -j ACCEPT

# Ensure IP forwarding is enabled (optional, handled by NM in shared mode)
echo 1 | sudo tee /proc/sys/net/ipv4/ip_forward

# Optional: Restart Avahi Daemon for mDNS support
(sleep 15 && sudo systemctl restart avahi-daemon) &

# Start the hotspot
nmcli connection up Hotspot

# restart touchosc to work with the new connection
systemctl restart mod-touchosc2midi 2>/dev/null
