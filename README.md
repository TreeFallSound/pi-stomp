# pi-Stomp!
#### pi-Stomp is a DIY high definition, multi-effects stompbox platform for guitar bass and keyboards
For more info about what it is and what it can do, go to [treefallsound.com](https://treefallsound.com)

## pi-Stomp Software and Firmware
We start with a 64-bit Raspberry Pi lite operating system.  We then add MOD, which is an open source audio host & UI
created by the awesome folk at moddevices.com

The pi-Stomp hardware requires drivers to interface with the LCD, potentiometers, encoders, footswitches, MIDI, etc.

A pi-Stomp software service, mod-ala-pi-stomp, uses the drivers to monitor all input devices, to drive the LCD
and to, among other things, send commands to mod-host for reading/writing pedalboard configuration information. 

This repository includes:
* the pi-Stomp hardware drivers ('pistomp' module)
* the mod-ala-pi-stomp service ('modalapistomp.py' & 'modalapi' module)
* setup scripts for downloading/installing the above along with:
  * python dependencies
  * MOD software
  * sound card drivers
  * system tweaks
  * hundreds of LV2 plugins
  * sample pedalboards

## Installing
For full installation instructions including etching the initial operating system, see [this guide](https://www.treefallsound.com/wiki/doku.php?id=software_installation_64-bit)

After first boot, establish an ssh session to the RPi (the password is the one set during OS install):

        ssh pistomp@pistomp.local
        
Once connected, download the pi-Stomp software:
        
        sudo apt update --allow-releaseinfo-change --fix-missing && sudo apt install -y git
        
        git clone https://github.com/TreeFallSound/pi-stomp.git
        
        cd pi-stomp
        
Now run the setup utility to install the software and audio plugins.  It could take over a half hour.
There are a few setup options based on your system hardware.
Typical systems should run:
        
        nohup ./setup.sh > setup.log | tail -f setup.log
        
The IQAudio Codec Zero is the default audio card, so the above command is equivalent to adding `-a iqaudio-codec`
(eg: ./setup.sh -a iqaudio-codec).
For an audioInjector card, add: `-a
audioinjector-wm8731-audio`  For HiFiBerry add: `-a hifiberry-dacplusadc`
For the original v1.x hardware, add `-v 1.0`

If all went well, the system will reboot, then finally display the default pedalboard
