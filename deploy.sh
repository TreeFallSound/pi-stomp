#!/bin/bash
set -e

HOST="pistomp@pistomp.local"
DEST="/home/pistomp/pi-stomp"

# Two device layouts are supported:
#   old world: ~/pi-stomp is a plain user-owned directory  -> plain rsync
#   new world: ~/pi-stomp is a symlink to the root-owned, pacman-packaged
#              /opt/pistomp/pi-stomp tree                  -> rsync via `sudo rsync`
# Detect which one we're on and only elevate if the target is a symlink.
RSYNC_OPTS=(-az --exclude='__pycache__/' --exclude='*.pyc')
SUDO=""
if ssh "${HOST}" "test -L ${DEST}"; then
    echo "Detected packaged layout (~/pi-stomp is a symlink); writing with sudo on device."
    RSYNC_OPTS+=(--rsync-path="sudo rsync")
    SUDO="sudo "
fi

# Source folders and top-level files to deploy. Directories are copied
# wholesale; __pycache__/*.pyc are filtered via RSYNC_OPTS.
PATHS=(modalapistomp.py modalapi pistomp common fonts images ui uilib util)
[ -d blend ] && PATHS+=(blend)

echo "Deploying Python files to pistomp..."

# wifi.py became the wifi/ package; rsync (no --delete) won't drop the stale file.
ssh "${HOST}" "${SUDO}rm -f ${DEST}/modalapi/wifi.py"

rsync "${RSYNC_OPTS[@]}" "${PATHS[@]}" "${HOST}:${DEST}/"

echo "Restarting service..."
ssh "${HOST}" "sudo systemctl restart mod-ala-pi-stomp"

# Tail logs during startup (2 seconds) then check status
echo "Service starting, showing logs..."
echo "----------------------------------------"
ssh "${HOST}" "timeout 2 sudo journalctl -u mod-ala-pi-stomp -f --since '1 second ago' 2>/dev/null || true"
echo "----------------------------------------"

# Check if service started successfully
if ssh "${HOST}" "sudo systemctl is-active --quiet mod-ala-pi-stomp"; then
    echo "Service started successfully."
else
    echo "ERROR: Service failed to start!"
    echo "----------------------------------------"
    echo "Service status:"
    ssh "${HOST}" "sudo systemctl status mod-ala-pi-stomp"
    exit 1
fi

exit 0
