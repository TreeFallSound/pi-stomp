#!/bin/bash

Sudo apt install -y lockfile-progs

mkdir -p $HOME/data/config
mkdir -p "$HOME/data/user-files/Aida DSP Models"

ln -s $HOME/data/.pedalboards /home/pistomp/.pedalboards
ln -s $HOME/.lv2 /home/pistomp/data/.lv2

#move default config files to data dir
cp $HOME/pi-stomp/setup/config_templates/default_config.yml $HOME/data/config

#USB automounter
sudo dpkg -i /home/pistomp/pi-stomp/setup/mod/usbmount.deb