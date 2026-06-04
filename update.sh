#!/bin/bash
# Update the pistomp device to the latest and greatest
set -euo pipefail

SERVICE_FILE="/usr/lib/systemd/system/mod-ala-pi-stomp.service"

# Exits early on uncommitted changes
git diff --exit-code || { echo "Uncommitted changes found. Exiting."; exit 1; }
git pull --ff-only

# Discover the venv dir from the service file
PYTHON_BIN=$(grep '^ExecStart=' "$SERVICE_FILE" | awk '{print $1}' | sed 's/ExecStart=//')
VENV_DIR=$(dirname "$(dirname "$PYTHON_BIN")")

sudo UV_PROJECT_ENVIRONMENT="$VENV_DIR" uv sync --frozen --no-dev --extra hardware
