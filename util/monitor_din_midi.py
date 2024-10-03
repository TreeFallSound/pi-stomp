#!/usr/bin/env python3

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

import serial

#ser = serial.Serial('/dev/ttyAMA0', baudrate=31250)
ser = serial.Serial('/dev/ttyAMA0', baudrate=38400)    

message = [0, 0, 0]
while True:
  i = 0
  while i < 3:
    data = ord(ser.read(1)) # read a byte
    if data >> 7 != 0:  
      i = 0      # status byte!   this is the beginning of a midi message!
    message[i] = data
    i += 1
    if i == 2 and message[0] >> 4 == 12:  # program change: don't wait for a
      message[2] = 0                      # third byte: it has only 2 bytes
      i = 3

  messagetype = message[0] >> 4
  messagechannel = (message[0] & 15) + 1
  note = message[1] if len(message) > 1 else None
  velocity = message[2] if len(message) > 2 else None
  print('msg %d' % velocity)
  if messagetype == 9:    # Note on
    print('Note on')
  elif messagetype == 8:  # Note off
    print( 'Note off')            
  elif messagetype == 12: # Program change
    print( 'Program change')
