#!/bin/bash

# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

# Select the pi-Stomp audio card for the next boot.
#
# Usage: change-audio-card.sh <overlay>
#   overlay: iqaudio-codec | hifiberry-dacplusadc | audioinjector-wm8731-audio
#
# Enables the dtoverlay for the selected card (and disables the other known
# cards) in /boot/firmware/config.txt, then seeds the matching known-good
# ALSA state via pistomp-audio's seed.sh so the next boot starts with a
# working mixer configuration.
#
# The overlay name is the only key in the chain: recovery's
# AUDIO_CARD_OVERLAYS, the menu selection, this script, and seed.sh all pass
# it unchanged. Keep the lists in step: pistomp-recovery constants.py,
# change-audio-card.sh, seed.sh, and the image's config.txt.

set -euo pipefail

cards=("audioinjector-wm8731-audio" "iqaudio-codec" "hifiberry-dacplusadc")
config_file=/boot/firmware/config.txt
seed=/usr/lib/pistomp/alsa/seed.sh

if [ $# -eq 0 ]; then
  PS3="Select a card: "
  select opt in ${cards[@]}; do
     if [[ " ${cards[*]} " =~ " ${opt} " ]]; then
       break
     fi
  done
else
  opt=$1
fi

card_found=0
for c in ${cards[@]}; do
  if [[ "$opt" == "$c" ]]; then
    sudo sed -i "s/^\s*#dtoverlay=$c/dtoverlay=$c/" ${config_file}
    card_found=1
  else
    sudo sed -i "s/^\s*dtoverlay=$c/#dtoverlay=$c/" ${config_file}
  fi
done

if [[ ${card_found} -eq 1 ]]; then
  sudo ${seed} "$opt"

  echo "*******************************"
  echo "*  Reconfiguration complete.  *"
  echo "*  You can now:               *"
  echo "*  1) Manually power down     *"
  echo "*  2) Attach new card         *"
  echo "*  3) Restart                 *"
  echo "*******************************"
else
  echo "$opt is not a known card"
  exit 1
fi