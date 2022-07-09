#!/bin/sh
IN_PORT_ID=$(/usr/bin/touchosc2midi list ports 2>&1 | grep touchosc | head -n 1 | egrep -o "\s+[0-9]+: " | egrep -o "[0-9]+")
OUT_PORT_ID=$(/usr/bin/touchosc2midi list ports 2>&1 | grep touchosc | tail -n 1 | egrep -o "\s+[0-9]+: " | egrep -o "[0-9]+")
exec touchosc2midi --midi-in=$IN_PORT_ID --midi-out=$OUT_PORT_ID
