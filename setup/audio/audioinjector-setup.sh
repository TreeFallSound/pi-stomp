#!/bin/bash -e

deb_file=audio.injector.scripts_0.1-1_all.deb
wget https://github.com/Audio-Injector/stereo-and-zero/raw/master/${deb_file}

sudo dpkg -i ${deb_file} 

rm -f ${deb_file}

# Modify audioInjector-setup.sh to not run rpi-update
sudo sed -i 's/sudo rpi-update/#sudo rpi-update/' /usr/bin/audioInjector-setup.sh

# Execute setup
/usr/bin/audioInjector-setup.sh

# Change jack.service to use the audioinjector card
sudo sed -i -e 's/hw:pisound/hw:audioinjectorpi/' -e 's/-n 2/-n 3/' /usr/lib/systemd/system/jack.service

# Change amixer settings
sudo cp setup/audio/asound.state.RCA.thru.test /usr/share/doc/audioInjector/asound.state.RCA.thru.test
