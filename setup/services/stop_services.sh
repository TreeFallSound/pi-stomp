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

sudo systemctl disable hciuart.service
sudo systemctl stop hciuart.service
#sudo systemctl mask --now hciuart.service

# pisound services only needed for pisound hardware and can conflict with mod-ala-pi-stomp service
sudo systemctl mask --now pisound-btn.service
sudo systemctl mask --now pisound-ctl.service

# VNC server disabled to save CPU when not usally required
sudo systemctl mask --now vncserver-x11-serviced.service
