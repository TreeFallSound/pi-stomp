#!/usr/bin/env bash
# Deploy pi-stomp source to the device via rsync and restart the service.
# Override PISTOMP_HOST / PISTOMP_USER if your device differs from the default.
set -euo pipefail

HOST="${PISTOMP_HOST:-pistomp.local}"
USER="${PISTOMP_USER:-pistomp}"
TARGET="${USER}@${HOST}"
REMOTE_DIR="/home/pistomp/pi-stomp"

echo "==> Deploying to ${TARGET}"

rsync -az --delete --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.git' --exclude='.gitignore' --exclude='tests' \
    --exclude='setup' --exclude='*.md' --exclude='*.yml' --exclude='*.yaml' \
    --exclude='*.json' --exclude='*.toml' --exclude='*.lock' \
    --exclude='*.png' --exclude='*.jpg' --exclude='*.svg' \
    ./ \
    "${TARGET}:${REMOTE_DIR}/"

echo "==> Restarting mod-ala-pi-stomp"
ssh "${TARGET}" 'sudo systemctl restart mod-ala-pi-stomp'

echo "==> Done"
