#!/bin/bash -e

sudo cp setup/services/* /usr/lib/systemd/system/
sudo ln -sf /usr/lib/systemd/system/mod-ala-pi-stomp.service /etc/systemd/system/multi-user.target.wants
sudo ln -sf /usr/lib/systemd/system/ttymidi.service /etc/systemd/system/multi-user.target.wants