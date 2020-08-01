#!/bin/bash -e

orig="LV2_PATH=/usr/local/modep/.lv2$"
new="LV2_PATH=/usr/local/modep/.lv2:/home/modep/.lv2"
sudo sed -i "s|$orig|$new|" /usr/lib/systemd/system/mod-host.service
sudo sed -i "s|$orig|$new|" /usr/lib/systemd/system/mod-ui.service

