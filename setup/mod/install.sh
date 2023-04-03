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

set -x

#Install Dependancies
sudo apt-get -y install virtualenv python3-pip python3-dev build-essential libasound2-dev libjack-jackd2-dev liblilv-dev libjpeg-dev zlib1g-dev cmake debhelper dh-autoreconf dh-python gperf intltool ladspa-sdk libarmadillo-dev libasound2-dev libavahi-gobject-dev libavcodec-dev libavutil-dev libbluetooth-dev libboost-dev libeigen3-dev libfftw3-dev libglib2.0-dev libglibmm-2.4-dev libgtk2.0-dev libgtkmm-2.4-dev libjack-jackd2-dev libjack-jackd2-dev liblilv-dev liblrdf0-dev libsamplerate0-dev libsigc++-2.0-dev libsndfile1-dev libsndfile1-dev libzita-convolver-dev libzita-resampler-dev lv2-dev p7zip-full python3-all python3-setuptools libreadline-dev zita-alsa-pcmi-utils hostapd dnsmasq iptables python3-smbus python3-dev liblo-dev libzita-alsa-pcmi-dev authbind rcconf libfluidsynth-dev lockfile-progs

#Install Python Dependancies
sudo pip3 install pyserial==3.0 pystache==0.5.4 aggdraw==1.3.11 scandir backports.shutil-get-terminal-size
sudo pip3 install pycrypto
sudo pip3 install tornado==4.3
sudo pip3 install Pillow==8.4.0
sudo pip3 install cython

#Install Mod Software
mkdir -p /home/pistomp/data/.pedalboards
mkdir -p /home/pistomp/data/user-files
mkdir -p /home/pistomp/data/configs
sudo mkdir -p /usr/mod/scripts
cd /home/pistomp/data/user-files
mkdir -p "Speaker Cabinets IRs"
mkdir -p "Reverb IRs"
mkdir -p "Audio Loops"
mkdir -p "Audio Recordings"
mkdir -p "Audio Samples"
mkdir -p "Audio Tracks"
mkdir -p "MIDI Clips"
mkdir -p "MIDI Songs"
mkdir -p "Hydrogen Drumkits"
mkdir -p "SF2 Instruments"
mkdir -p "SFZ Instruments"
mkdir -p "Amplifier Profiles"
mkdir -p "Aida DSP Models"

#Jack2
pushd $(mktemp -d) && git clone https://github.com/moddevices/jack2.git
pushd jack2
./waf configure
./waf build
sudo ./waf install

#Browsepy
pushd $(mktemp -d) && git clone https://github.com/micahvdm/browsepy.git
pushd browsepy
sudo pip3 install ./

#Mod-host
pushd $(mktemp -d) && git clone https://github.com/moddevices/mod-host.git
pushd mod-host
make
sudo make install

#Mod-ui
pushd $(mktemp -d) && git clone https://github.com/moddevices/mod-ui.git
pushd mod-ui
chmod +x setup.py
cd utils
make
cd ..
sudo ./setup.py install
cp -r default.pedalboard /home/pistomp/data/.pedalboards

#Touchosc2midi
pushd $(mktemp -d) && git clone https://github.com/BlokasLabs/amidithru.git
pushd amidithru
sed -i 's/CXX=g++.*/CXX=g++/' Makefile
sudo make install

pushd $(mktemp -d) && git clone https://github.com/BlokasLabs/touchosc2midi.git
pushd touchosc2midi
sudo pip3 install ./

cd /home/pistomp

ln -s /home/pistomp/data/.pedalboards /home/pistomp/.pedalboards
ln -s /home/pistomp/.lv2 /home/pistomp/data/.lv2

cd /home/pistomp/pi-stomp/setup/mod

#Create Services
sudo cp *.service /usr/lib/systemd/system/
sudo ln -sf /usr/lib/systemd/system/browsepy.service /etc/systemd/system/multi-user.target.wants
sudo ln -sf /usr/lib/systemd/system/jack.service /etc/systemd/system/multi-user.target.wants
sudo ln -sf /usr/lib/systemd/system/mod-host.service /etc/systemd/system/multi-user.target.wants
sudo ln -sf /usr/lib/systemd/system/mod-ui.service /etc/systemd/system/multi-user.target.wants
sudo ln -sf /usr/lib/systemd/system/mod-amidithru.service /etc/systemd/system/multi-user.target.wants
sudo ln -sf /usr/lib/systemd/system/mod-touchosc2midi.service /etc/systemd/system/multi-user.target.wants

#Create users and groups so services can run as user instead of root
sudo adduser --no-create-home --system --group jack
sudo adduser pistomp jack --quiet
sudo adduser root jack --quiet
sudo adduser jack audio --quiet
sudo cp jackdrc /etc/
sudo chmod +x /etc/jackdrc
sudo chown jack:jack /etc/jackdrc
sudo cp 80 /etc/authbind/byport/
sudo chmod 500 /etc/authbind/byport/80
sudo chown pistomp:pistomp /etc/authbind/byport/80

#Copy WiFi hotspot files
sudo cp hotspot/etc/default/hostapd.pistomp /etc/default
sudo cp hotspot/etc/dnsmasq.d/wifi-hotspot.conf /etc/dnsmasq.d
sudo cp hotspot/etc/hostapd/hostapd.conf /etc/hostapd
sudo cp -R hotspot/usr/lib/pistomp-wifi /usr/lib
sudo cp hotspot/usr/lib/systemd/system/wifi-hotspot.service /usr/lib/systemd/system
sudo chown -R pistomp:pistomp /usr/lib/pistomp-wifi
sudo chmod +x -R /usr/lib/pistomp-wifi

#move default config files to data dir
cd ../../pistomp
cp default* /home/pistomp/data/configs

#USB automounter
sudo dpkg -i /home/pistomp/pi-stomp/setup/mod/usbmount.deb