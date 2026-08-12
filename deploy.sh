#!/usr/bin/env bash

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

# Deploy pi-stomp source to the device via rsync and restart the service.
# Override PISTOMP_HOST / PISTOMP_USER if your device differs from the default.
set -euo pipefail

HOST="${PISTOMP_HOST:-pistomp.local}"
USER="${PISTOMP_USER:-pistomp}"
TARGET="${USER}@${HOST}"
REMOTE_DIR="/home/pistomp/pi-stomp"

echo "==> Deploying to ${TARGET}"

rsync -az --delete \
    --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.pytest_cache' --exclude='.ruff_cache' --exclude='.coverage' \
    --exclude='.DS_Store' --exclude='.claude' --exclude='.github' \
    --exclude='typings' \
    --exclude='.git' --exclude='.gitignore' --exclude='tests' \
    --exclude='setup' --exclude='*.md' --exclude='*.yml' --exclude='*.yaml' \
    --exclude='*.json' --exclude='*.toml' --exclude='*.lock' \
    --filter='protect .git-meta' \
    ./ \
    "${TARGET}:${REMOTE_DIR}/"

echo "==> Restarting mod-ala-pi-stomp"
ssh "${TARGET}" 'sudo systemctl restart mod-ala-pi-stomp'

echo "==> Service starting, showing logs..."
echo "----------------------------------------"
ssh "${TARGET}" "timeout 2 sudo journalctl -u mod-ala-pi-stomp -f --since '1 second ago' 2>/dev/null || true"
echo "----------------------------------------"

if ssh "${TARGET}" 'sudo systemctl is-active --quiet mod-ala-pi-stomp'; then
    echo "==> Service started successfully."
else
    echo "ERROR: Service failed to start!"
    echo "----------------------------------------"
    echo "Service status:"
    ssh "${TARGET}" 'sudo systemctl status mod-ala-pi-stomp'
    exit 1
fi

echo "==> Done"
