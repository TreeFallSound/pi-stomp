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
    echo "Usage: $(basename $0) [-v <hardware_version>] [-m]"
    echo ""
    echo "Options:"
    echo " -v <version>          Specify hardware version"
    echo "                         1.0 : original pi-Stomp hardware (PCB v1)"
    echo "                         2.0 : most hardware (default)"
    echo " -m                    Enable MIDI via UART"
    echo " -h                    Display this message"    
}

has_ttymidi=false

while getopts ':v:' o; do
    case "${o}" in
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

printf "\n===== OS update =====\n"
sudo apt-get update -y --allow-releaseinfo-change --fix-missing

printf "\n===== Audio card setup =====\n"
setup/audio/audiocard-setup.sh

printf "\n===== Modep software module install =====\n"
patchbox module activate modep

printf "\n===== Mod software tweaks =====\n"
setup/mod-tweaks/mod-tweaks.sh

printf "\n===== Install pi-stomp package dependencies =====\n"
setup/pkgs/simple_install.sh
setup/pkgs/gfxhat_install.sh
setup/pkgs/lilv_install.sh
setup/pkgs/mod-ttymidi_install.sh

printf "\n===== Get extra plugins =====\n"
setup/plugins/build_extra_plugins.sh

printf "\n===== Get example pedalboards =====\n"
setup/pedalboards/get_pedalboards.sh

printf "\n===== System tweaks =====\n"
setup/sys/config_tweaks.sh
cp setup/sys/bash_aliases ~/.bash_aliases

printf "\n===== Manage services =====\n"
setup/services/create_services.sh
setup/services/tweak_services.sh
setup/services/stop_services.sh

printf "\n===== pi-stomp setup complete =====\n"

