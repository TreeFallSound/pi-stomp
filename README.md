# pi-Stomp!
#### pi-Stomp is a DIY high definition, multi-effects stompbox platform for guitar, bass and keyboards
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
* setup scripts (deprecated support - see below) for downloading/installing the above along with:
  * python dependencies
  * MOD software
  * sound card drivers
  * system tweaks
  * hundreds of LV2 plugins
  * sample pedalboards

## Installing
For full installation instructions, see [this guide](https://www.treefallsound.com/wiki/doku.php?id=software_installation_3.x)

Those instructions start with a pre-built pi-Stomp image.  The supporting packages are pre-installed.
This is the recommended method of installation for most users.

This [pi-gen-pistomp](https://github.com/TreeFallSound/pi-gen-pistomp) repository is used to create the pre-built images.
We recommend forking this for creating your own modified images.

The now deprecated method of using the setup scripts in this repository to build from scratch is another option.
You can start with a base RPi image and use these
[2.x install instructions](https://www.treefallsound.com/wiki/doku.php?id=software_installation_64-bit),
but note that the setup scripts have not been updated to work with the newer v3 hardware so you are on your own there.
Also keep in mind that there are hundreds of packages used to build the system.
Package version incompatibilities are much more likely using this method.

## Running tests

Run tests using `pytest` in the virtual environment. There is a Github Actions workflow that runs this in CI as well.

If you are writing new snapshot tests, or experiencing unexpected snapshot assertion failures, try running `pytest --snapshot-update` and inspect the diff. Sometimes there are cross-platform differences; use PIL tweaks in `conftest.py` to align them.

## Running the emulator

The emulator runs the pi-Stomp UI on macOS or Linux desktop, with no Pi hardware required. In this mode, pedalboards are provided by running [MOD Desktop](https://mod.audio/desktop/) locally as well.

We also need to install [lilv](https://drobilla.net/docs/lilv/), which is not available via PyPI, but is required for parsing pedalboard bundles. The [run_emulator.sh](./run_emulator.sh) script will discover it automatically after installation:

```bash
brew install lilv pkg-config  # macos
sudo apt install liblilv-dev python3-lilv pkg-config  # debian/ubuntu
sudo pacman -S lilv pkgconf  # arch
```

Then sync and run:

```sh
uv sync
./run_emulator.sh  # can pass v1/v2/v3; defaults to v3
```
