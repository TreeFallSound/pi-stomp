# pi-Stomp!
#### pi-Stomp is a DIY high definition, multi-effects stompbox platform for guitar bass and keyboards
For more info about what it is and what it can do, go to [treefallsound.com](https://treefallsound.com)

## pi-Stomp Software and Firmware
The raspberry pi inside a pi-Stomp runs a Raspbian based OS created by blokaslabs called [Patchbox OS](https://blokas.io/patchbox-os/)

Patchbox OS includes a module called modep which is a port of MOD for raspberry pi.  modep/MOD provide the audio host
(mod-host) and UI (mod-ui) for pi-Stomp

The pi-Stomp hardware requires drivers to interface with potentiometers, encoders, footswitches, MIDI, LCD, etc.

A pi-Stomp software service, mod-ala-pi-stomp, uses the drivers to monitor all input devices, to drive the LCD
and to send commands to mod-host for reading/writing pedalboard configuration information.

This repository includes:
* the pi-Stomp hardware drivers ('pistomp' module)
* the mod-ala-pi-stomp service ('modalapistomp.py' & 'modalapi' module)
* setup scripts for downloading/installing the above plus:
  * python dependencies
  * the 'modep' module for patch OS
  * sound card drivers
  * system tweaks
  * hundreds of LV2 plugins
  * sample pedalboards

## Installing
Patch OS must first be installed.  See [this guide](https://blokas.io/patchbox-os/docs/first-run-options/)

After first boot, set up networking so that you can ssh

        ssh patch@patchbox.local
Once connected, download the software:
        
        git clone https://github.com/TreeFallSound/pi-stomp.git
        
        cd pi-stomp
        
Now run the setup utility to install the software and audio plugins.  It could take about a half hour.
For most hardware, including pi-Stomp Core, just run:
        
        ./setup.sh
        
For the original pi-Stomp hardware (pcb versions 1.x) pass the version to the setup script:
        
        ./sethup.sh -v 1.0

If all went well, you can then reboot

        sudo reboot