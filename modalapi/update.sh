#!/bin/bash -e

#Script to update and check if necessary software additions are installed.

#First up is to apt-get update and fix the bulleye bugs
sudo apt-get update --allow-releaseinfo-change --fix-missing

#Change directory to pi-stomp and pull latest updates from github
cd ~patch/pi-stomp
git pull

#Additional software that gets added should be added here as an install, even if it's not seen as required.
#This prevents things from breaking for current users who are updating.
FILE=/home/patch/pi-stomp/requirements.txt
if [ -f "$FILE" ]; then
    sudo pip3 install -r requirements.txt
fi
