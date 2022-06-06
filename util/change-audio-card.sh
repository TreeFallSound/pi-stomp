#!/bin/bash

cards=("audioinjector-wm8731-audio" "iqaudio-codec" "hifiberry-dacplusadc")
config_file=/boot/config.txt
state_file=/var/lib/alsa/asound.state

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

# Enable the dtoverlay for the selected card, comment out the others
card_found=0
for c in ${cards[@]}; do
  if [[ "$opt" == "$c" ]]; then
    sudo sed -i "s/^\s*#dtoverlay=$c/dtoverlay=$c/" ${config_file}
    echo "$c card enabled in ${config_file}"
    card_found=1
  else
    sudo sed -i "s/^\s*dtoverlay=$c/#dtoverlay=$c/" ${config_file}
  fi
done

if [[ ${card_found} -eq 1 ]]; then
  # remove the state file so that the card specific state file will be loaded next time modalapistomp starts
  sudo rm -f ${state_file}

  echo "*******************************"
  echo "*  Reconfiguration complete.  *"
  echo "*  You can now:               *"
  echo "*  1) Manually power down     *"
  echo "*  2) Attach new card         *"
  echo "*  3) Restart                 *"
  echo "*******************************"
else
  echo "$opt is not a known card"
fi
