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

set +e

sudo sed -i 's/#js-preset-enabler /js-preset-enabler /' /usr/local/modep/mod-ui/html/index.html

sudo patch -b -N -u /usr/local/modep/mod-ui/mod/host.py -i setup/mod-tweaks/host.diff

sudo patch -b -N -u /usr/local/modep/mod-ui/mod/session.py -i setup/mod-tweaks/session.diff

sudo patch -b -N -u /usr/local/modep/mod-ui/mod/webserver.py -i setup/mod-tweaks/webserver.diff

exit 0
