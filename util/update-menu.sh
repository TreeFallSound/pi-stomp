#!/bin/bash

mkdir -p /home/pistomp/data/configs
mkdir -p '/home/pistomp/data/user-files/Aida DSP Models'

ln -s /home/pistomp/data/.pedalboards /home/pistomp/.pedalboards
ln -s /home/pistomp/.lv2 /home/pistomp/data/.lv2

#move default config files to data dir
cd /home/pistomp/pi-stomp/pistomp
cp default* /home/pistomp/data/configs

#USB automounter
sudo dpkg -i /home/pistomp/pi-stomp/setup/mod/usbmount.deb