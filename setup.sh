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


#
# Usage and options
#
usage()
{
    echo "Usage: $(basename $0) [-a <audio_card>] [-v <hardware_version>] [-m]"
    echo ""
    echo "Options:"
    echo " -a <audio_card>       Specify audio card (audioinjector-wm8731-audio | iqaudio-codec | hifiberry-dacplusadc)"
    echo " -v <version>          Specify hardware version"
    echo "                         1.0 : original pi-Stomp hardware (PCB v1)"
    echo "                         2.0 : most hardware (default)"
    echo " -m                    Enable MIDI via UART"
    echo " -h                    Display this message"    
}

hardware_version=2.0
has_ttymidi=false

while getopts 'a:v:mh' o; do
    case "${o}" in
        a)
            audio_card=${OPTARG}
            ;;
        v)
            hardware_version=${OPTARG}
            ;;
	m)
	    has_ttymidi=true
            ;;
	h)
	    usage
	    exit 0
	    ;;
        *)
            usage 1>&2
	    exit 1
            ;;
    esac
done

export has_ttymidi

#
# Hardware specific
#
if [ -z ${hardware_version+x} ]; then
    printf "\nUsing default hardware configuration\n";
else
    printf "\n===== pi-Stomp mods for hardware version specified =====\n"
    ${HOME}/pi-stomp/setup/pi-stomp-tweaks/modify_version.sh ${hardware_version}
fi

printf "\n===== Audio card setup =====\n"
setup/audio/audiocard-setup.sh
if [ ! -z ${audio_card+x} ]; then
    util/change-audio-card.sh ${audio_card} || (usage; exit 1)
fi

printf "\n===== Mod software install =====\n"
setup/mod/install.sh

printf "\n===== Mod software tweaks =====\n"
setup/mod-tweaks/mod-tweaks.sh

printf "\n===== Install pi-stomp package dependencies =====\n"
setup/pkgs/simple_install.sh
setup/pkgs/lilv_install.sh
setup/pkgs/mod-ttymidi_install.sh
if awk "BEGIN {exit !($hardware_version < 2.0)}"; then
    printf "\n===== GFX HAT LCD support install =====\n"
    setup/pkgs/gfxhat_install.sh
fi

printf "\n===== Get extra plugins =====\n"
setup/plugins/get_plugins.sh

printf "\n===== Get example pedalboards =====\n"
setup/pedalboards/get_pedalboards.sh

printf "\n===== System tweaks =====\n"
setup/sys/config_tweaks.sh
cp setup/sys/bash_aliases ~/.bash_aliases

printf "\n===== Manage services =====\n"
setup/services/create_services.sh

printf "\n===== RT Kernel Install =====\n"
setup/sys/rtkernel.sh

printf "\n===== pi-stomp setup complete - rebooting =====\n"
sudo reboot now
