#!/bin/bash

Sudo apt install -y lockfile-progs

mkdir -p /home/pistomp/data/config_templates
mkdir -p '/home/pistomp/data/user-files/Aida DSP Models'

ln -s /home/pistomp/data/.pedalboards /home/pistomp/.pedalboards
ln -s /home/pistomp/.lv2 /home/pistomp/data/.lv2

#move default config files to data dir
cp /home/pistomp/pi-stomp/setup/config_templates/default* /home/pistomp/data/config_templates

#USB automounter
sudo dpkg -i /home/pistomp/pi-stomp/setup/mod/usbmount.deb