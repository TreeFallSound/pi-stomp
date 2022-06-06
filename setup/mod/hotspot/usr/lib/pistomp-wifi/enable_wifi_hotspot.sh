#!/bin/sh

# patchbox-wifi scripts for enabling/disabling wifi hotspot
#
# Copyright (C) 2017  Vilniaus Blokas UAB, https://blokas.io/pisound
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 2 of the
# License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#

rfkill unblock wifi
wpa_cli -i wlan0 disconnect
dhcpcd --denyinterfaces wlan0
ifconfig wlan0 down
ifconfig wlan0 172.24.1.1 netmask 255.255.255.0 broadcast 172.24.1.255
systemctl stop dnsmasq
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
iptables -A FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i wlan0 -o eth0 -j ACCEPT
echo 1 > /proc/sys/net/ipv4/ip_forward
systemctl start dnsmasq
(sleep 15 && systemctl restart avahi-daemon) &
systemctl unmask hostapd
systemctl start hostapd

systemctl restart touchosc2midi 2>/dev/null
