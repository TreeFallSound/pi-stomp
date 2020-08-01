#!/bin/bash -e

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

# System configuration tweaks
setup/sys/config_tweaks.sh

# Mod software tweaks
setup/mod-tweaks/mod-tweaks.sh

# Get extra plugins
setup/plugins/build_extra_plugins.sh

# Get example pedalboards
setup/pedalboards/get_pedalboards.sh

# Configure audio card
setup/audio/audioinjector-setup.sh
