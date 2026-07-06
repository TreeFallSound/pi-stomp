#!/bin/bash
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
