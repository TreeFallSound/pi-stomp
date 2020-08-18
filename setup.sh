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

# Configure audio card
setup/audio/audioinjector-setup.sh

# Install package dependencies
setup/pkgs/simple_install.sh
setup/pkgs/gfxhat_install.sh
setup/pkgs/lilv_install.sh 
setup/pkgs/mod-ttymidi_install.sh

# Create services
setup/services/create_services.sh

# Tweak services
setup/services/tweak_services.sh

# Stop services
setup/services/stop_services.sh

# Mod software tweaks
setup/mod-tweaks/mod-tweaks.sh

# Get extra plugins
setup/plugins/build_extra_plugins.sh

# Get example pedalboards
setup/pedalboards/get_pedalboards.sh

# System configuration tweaks
setup/sys/config_tweaks.sh
