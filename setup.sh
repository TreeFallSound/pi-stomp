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

printf "\n===== Audio card setup =====\n"
setup/audio/audioinjector-setup.sh

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

printf "\n===== System configuration tweaks =====\n"
setup/sys/config_tweaks.sh

printf "\n===== Manage services =====\n"
setup/services/create_services.sh
setup/services/tweak_services.sh
setup/services/stop_services.sh

printf "\n===== pi-stomp setup complete =====\n"

