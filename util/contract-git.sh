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

# contract-git.sh — revert the pi-stomp tree to its packaged (non-git) state.
#
# Inverse of expand-git.sh: removes the .git directory entirely. The files
# on disk are untouched — they're whatever dpkg last unpacked — so this
# just drops the git metadata expand-git.sh added. With no .git/EXPANDED
# marker (and no .git at all), pi-stomp and pistomp-recovery treat the tree
# as packaged again and `apt upgrade pi-stomp` works normally.
#
# Run on the device:
#     ~/pi-stomp/util/contract-git.sh
#
# WARNING: discards any fetched history and local commits. There's no
# packaged commit to fall back to — re-run expand-git.sh from scratch if
# you need git again later.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -d "$SRC_DIR/.git" ]; then
    echo "Not expanded — nothing to do."
    exit 0
fi

rm -rf "$SRC_DIR/.git"
echo "==> Removed .git — tree is back to packaged (non-git) state"
echo "==> apt upgrades for pi-stomp re-enabled"
