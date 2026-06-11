#!/bin/bash
set -e

HOST="pistomp@pistomp.local"
DEST="/home/pistomp/pi-stomp"

# Two device layouts are supported:
#   old world: ~/pi-stomp is a plain user-owned directory  -> plain rsync
#   new world: ~/pi-stomp is a symlink to the root-owned, pacman-packaged
#              /opt/pistomp/pi-stomp tree                  -> rsync via `sudo rsync`
# Detect which one we're on and only elevate if the target is a symlink.
RSYNC_OPTS=(-az)
SUDO=""
if ssh "${HOST}" "test -L ${DEST}"; then
    echo "Detected packaged layout (~/pi-stomp is a symlink); writing with sudo on device."
    RSYNC_OPTS+=(--rsync-path="sudo rsync")
    SUDO="sudo "
fi

push() { rsync "${RSYNC_OPTS[@]}" "$@"; }

echo "Deploying Python files to pistomp..."

# Copy Python files to device
push modalapistomp.py "${HOST}:${DEST}/"
push modalapi/*.py "${HOST}:${DEST}/modalapi/"
ssh "${HOST}" "${SUDO}rm -f ${DEST}/modalapi/wifi.py"
push modalapi/wifi/*.py "${HOST}:${DEST}/modalapi/wifi/"
push pistomp/*.py "${HOST}:${DEST}/pistomp/"
push pistomp/tuner/*.py "${HOST}:${DEST}/pistomp/tuner/"
if [ -d blend ]; then
    push blend "${HOST}:${DEST}/"
fi
push common "${HOST}:${DEST}/"
push fonts "${HOST}:${DEST}/"
push images "${HOST}:${DEST}/"
push ui "${HOST}:${DEST}/"
push uilib "${HOST}:${DEST}/"
push util "${HOST}:${DEST}/"

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
