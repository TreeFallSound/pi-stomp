#!/bin/bash -e

set +e

sudo sed -i 's/#js-preset-enabler /js-preset-enabler /' /usr/local/modep/mod-ui/html/index.html

sudo patch -b -N -u /usr/local/modep/mod-ui/mod/host.py -i setup/mod-tweaks/host.diff

sudo patch -b -N -u /usr/local/modep/mod-ui/mod/session.py -i setup/mod-tweaks/session.diff

sudo patch -b -N -u /usr/local/modep/mod-ui/mod/webserver.py -i setup/mod-tweaks/webserver.diff

exit 0
