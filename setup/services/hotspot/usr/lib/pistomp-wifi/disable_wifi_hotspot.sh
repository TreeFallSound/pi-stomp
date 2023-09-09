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

if [[ "$(systemctl is-system-running || true)" == "stopping" ]]; then
	exit
fi

rfkill unblock wifi
dhcpcd --allowinterfaces wlan0
systemctl stop hostapd
systemctl stop dnsmasq
systemctl disable hostapd
systemctl disable dnsmasq
ifconfig wlan0 0.0.0.0
echo | iptables-restore
echo 0 > /proc/sys/net/ipv4/ip_forward
iwlist wlan0 scan > /dev/null 2>&1
ifconfig wlan0 up
systemctl restart avahi-daemon
wpa_cli -i wlan0 reconnect
