#!/bin/bash
set -e

echo "Deploying Python files to pistomp..."

# Copy Python files to device
scp modalapistomp.py pistomp@pistomp.local:/home/pistomp/pi-stomp/
scp modalapi/*.py pistomp@pistomp.local:/home/pistomp/pi-stomp/modalapi/
ssh pistomp@pistomp.local "rm -f /home/pistomp/pi-stomp/modalapi/wifi.py"
scp modalapi/wifi/*.py pistomp@pistomp.local:/home/pistomp/pi-stomp/modalapi/wifi/
ssh pistomp@pistomp.local "mkdir -p /home/pistomp/pi-stomp/modalapi/ethernet"
scp modalapi/ethernet/*.py pistomp@pistomp.local:/home/pistomp/pi-stomp/modalapi/ethernet/
scp pistomp/*.py pistomp@pistomp.local:/home/pistomp/pi-stomp/pistomp/
scp pistomp/tuner/*.py pistomp@pistomp.local:/home/pistomp/pi-stomp/pistomp/tuner/
if [ -d blend ]; then
    scp -r blend pistomp@pistomp.local:/home/pistomp/pi-stomp/
fi
scp -r common pistomp@pistomp.local:/home/pistomp/pi-stomp/
scp -r fonts pistomp@pistomp.local:/home/pistomp/pi-stomp/
scp -r images pistomp@pistomp.local:/home/pistomp/pi-stomp/
scp -r ui pistomp@pistomp.local:/home/pistomp/pi-stomp/
scp -r uilib pistomp@pistomp.local:/home/pistomp/pi-stomp/
scp -r util pistomp@pistomp.local:/home/pistomp/pi-stomp/

echo "Restarting service..."
ssh pistomp@pistomp.local "sudo systemctl restart mod-ala-pi-stomp"

# Tail logs during startup (2 seconds) then check status
echo "Service starting, showing logs..."
echo "----------------------------------------"
ssh pistomp@pistomp.local "timeout 2 sudo journalctl -u mod-ala-pi-stomp -f --since '1 second ago' 2>/dev/null || true"
echo "----------------------------------------"

# Check if service started successfully
if ssh pistomp@pistomp.local "sudo systemctl is-active --quiet mod-ala-pi-stomp"; then
    echo "Service started successfully."
else
    echo "ERROR: Service failed to start!"
    echo "----------------------------------------"
    echo "Service status:"
    ssh pistomp@pistomp.local "sudo systemctl status mod-ala-pi-stomp"
    exit 1
fi

exit 0
