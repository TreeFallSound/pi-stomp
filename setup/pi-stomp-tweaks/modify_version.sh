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

if [ -z "$1" ]
  then
    echo "Requires version"
    echo "Usage: $(basename $0) <version_number>"
    exit
fi

jackdrc_file="/etc/jackdrc"
config_dir="$HOME/data/config"
config_file="$config_dir/default_config.yml"
hwfile="$config_dir/hardware-descriptor.json"

template_dir="$HOME/pi-stomp/setup/config_templates"
pistomp_orig_config_file="$template_dir/default_config_pistomp.yml"
pistomp_core_config_file="$template_dir/default_config_3fs_2knob_exp.yml"
pistomp_tre_config_file="$template_dir/default_config_pistomptre.yml"
default_hwfile="$template_dir/default-hardware-descriptor.json"

mkdir -p $config_dir

cp $default_hwfile $hwfile

if awk "BEGIN {exit !($1 >= 3.0 )}"; then
    cp $pistomp_tre_config_file $config_file
    sudo sed -i 's/-p [0-9]\+/-p 128/' $jackdrc_file
elif awk "BEGIN {exit !($1 >= 2.0 )}"; then
    cp $pistomp_core_config_file $config_file
    sudo sed -i 's/-p [0-9]\+/-p 256/' $jackdrc_file
elif awk "BEGIN {exit !($1 >= 1.0 )}"; then
    cp $pistomp_orig_config_file $config_file
    sudo sed -i 's/-p [0-9]\+/-p 256/' $jackdrc_file
fi

sed -i "s/version: [0-9]\.*[0-9]*\.*[0-9]*/version: $1/" $config_file

printf "\nHardware version changed to: $1\n"
