# Third-Party Licenses

This document lists third-party software components included in or distributed with this project's Raspberry Pi OS image and software stack, along with their respective licenses. It is provided to satisfy attribution and license-disclosure obligations for all bundled open source components.

> **Scope:** This file covers the contents of the **pi-gen-pistomp built OS image** released for download — the full system that runs on the device, including the OS, system services (jack2, mod-host, mod-ui, etc.), Python runtime dependencies, and LV2 plugins. It does **not** describe the contents of this Git repository, which contains only this project's own Python source code, licensed under AGPL-3.0-or-later. The components below are not part of the repository itself; they are installed, built, or bundled into the image by the pi-gen-pistomp build process.

**This project's own code is licensed under AGPL-3.0-or-later.** Components below are run as independent system services or separate processes (communicating via IPC, D-Bus, sockets, or HTTP) rather than linked into this project's codebase, except where noted.

> **A note on accuracy:** This file was compiled largely through automated extraction — `pip-licenses` for Python dependencies, `lilv`/TTL metadata inspection for LV2 plugins, and manual verification where automated tools returned incomplete or ambiguous results. Open source metadata is not always accurate or complete at the source, and errors or omissions may exist despite best efforts to verify each entry. If you are a rights holder or maintainer and believe an entry here is missing, incorrect, or needs attribution changes, please [open an issue](../../issues) or contact the maintainer of this repository.

## Contents

- [Core System Components (Cloned / Built from Source)](#core-system-components-cloned--built-from-source)
- [Python Dependencies](#python-dependencies)
- [LV2 Audio Plugins](#lv2-audio-plugins)

---

## Core System Components (Cloned / Built from Source)

These are the core audio/MIDI services and supporting tools built from source and included in the system image. Each runs as an independent process or service.

| Component | Version | License | Author / Maintainer | Source |
|---|---|---|---|---|
| amidithru | 1.0-3 | GPL v2+ | BlokasLabs | [github.com/BlokasLabs/amidithru](https://github.com/BlokasLabs/amidithru.git) |
| browsepy | 0.5 | MIT | mod-audio | [github.com/micahvdm/browsepy](https://github.com/micahvdm/browsepy.git) |
| hylia | 1.0.1 | GPL v2+ | FalkTX | [github.com/falkTX/Hylia](https://github.com/falkTX/Hylia.git) |
| jack-example-tools | Debian release 4-4 | GPL 2 | Debian Multimedia Team | [salsa.debian.org/multimedia-team/jack-example-tools](https://salsa.debian.org/multimedia-team/jack-example-tools.git) |
| jack2 | 1.9.22 | GPL 2 | jackaudio | [github.com/jackaudio/jack2](https://github.com/jackaudio/jack2.git) |
| mod-host | 0.10.6 | GPL v3+ | mod-audio | [github.com/mod-audio/mod-host](https://github.com/mod-audio/mod-host) |
| mod-midi-merger | None | ISC | mod-audio | [github.com/mod-audio/mod-midi-merger](https://github.com/mod-audio/mod-midi-merger) |
| mod-ttymidi | None | GPL | mod_audio | [github.com/moddevices/mod-ttymidi](https://github.com/moddevices/mod-ttymidi.git) |
| mod-ui | v0.99.8 | AGPL-3.0 | mod-audio | [github.com/TreeFallSound/mod-ui](https://github.com/TreeFallSound/mod-ui.git) |
| pi-gen | 2025-11-24-raspios-bookworm-arm64 | BSD-3-Clause | RPi-Distro | [github.com/RPi-Distro/pi-gen](https://github.com/RPi-Distro/pi-gen) |
| touchosc2midi | 0.0.12 | MIT | BlokasLabs | [github.com/BlokasLabs/touchosc2midi](https://github.com/BlokasLabs/touchosc2midi.git) |

> **Note:** `mod-ui` is distributed from this project's own fork (TreeFallSound/mod-ui), tracking upstream mod-audio/mod-ui, AGPL-3.0.

---

## Python Dependencies

Python packages installed in the runtime environment, extracted via `pip-licenses`. Runtime packages are listed below; additional packages used only for development, linting, or documentation are listed separately and are not part of the distributed runtime image.

### Runtime Dependencies

| Package | Version | License | Source |
|---|---|---|---|
| aggdraw | 1.3.11 | Python (MIT style) | [link](https://github.com/pytroll/aggdraw) |
| appdirs | 1.4.4 | MIT License | [link](http://github.com/ActiveState/appdirs) |
| async-timeout | 4.0.2 | Apache Software License | [link](https://github.com/aio-libs/async-timeout) |
| backports.shutil-get-terminal-size | 1.0.0 | MIT License | [link](https://github.com/chrippa/backports.shutil_get_terminal_size) |
| blinker | 1.9.0 | MIT License | [link](https://github.com/pallets-eco/blinker/) |
| browsepy | 0.5.6 | MIT License | [link](https://github.com/ergoithz/browsepy) |
| certifi | 2022.9.24, 2026.5.20 | Mozilla Public License 2.0 (MPL 2.0) | [link](https://github.com/certifi/python-certifi) |
| cffi | 2.0.0 | MIT | [link](https://cffi.readthedocs.io/en/latest/whatsnew.html) |
| chardet | 5.1.0 | GNU Lesser General Public License v2 or later (LGPLv2+) | [link](https://github.com/chardet/chardet) |
| charset-normalizer | 3.0.1 | MIT License | [link](https://github.com/Ousret/charset_normalizer) |
| click | 8.4.1 | BSD-3-Clause | [link](https://github.com/pallets/click/) |
| colorzero | 2.0 | BSD License | — |
| Cython | 3.2.5 | Apache-2.0 | [link](https://cython.org/) |
| distro | 1.8.0 | Apache Software License | [link](https://github.com/python-distro/distro) |
| filelock | 3.9.0 | The Unlicense (Unlicense) | [link](https://github.com/tox-dev/py-filelock) |
| Flask | 3.1.3 | BSD-3-Clause | [link](https://github.com/pallets/flask/) |
| gpiozero | 2.0.1 | BSD License | [link](https://gpiozero.readthedocs.io/) |
| idna | 3.3 | BSD License | [link](https://github.com/kjd/idna) |
| ifaddr | 0.1.7 | MIT License | [link](https://github.com/pydron/ifaddr) |
| itsdangerous | 2.2.0 | BSD License | [link](https://github.com/pallets/itsdangerous/) |
| JACK-Client | 0.5.5 | MIT License | [link](http://jackclient-python.readthedocs.io/) |
| Jinja2 | 3.1.6 | BSD License | [link](https://github.com/pallets/jinja/) |
| lgpio | 0.2.2.0 | unlicense.org | [link](http://abyz.me.uk/lg/py_lgpio.html) |
| MarkupSafe | 3.0.3 | BSD-3-Clause | [link](https://github.com/pallets/markupsafe/) |
| mido | 1.1.24 | MIT | [link](https://mido.readthedocs.io/) |
| mod | 0.99.8 | GPLv3 | [link](http://moddevices.com/) |
| netifaces | 0.10.5 | MIT License | [link](https://bitbucket.org/al45tair/netifaces) |
| numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | [link](https://numpy.org) |
| packaging | 26.2 | Apache-2.0 OR BSD-2-Clause | [link](https://github.com/pypa/packaging) |
| pigpio | 1.78 | unlicense.org | [link](http://abyz.me.uk/rpi/pigpio/python.html) |
| Pillow | 9.4.0 | Historical Permission Notice and Disclaimer (HPND) | [link](https://python-pillow.org) |
| platformdirs | 2.6.0 | MIT License | [link](https://github.com/platformdirs/platformdirs) |
| pyaml | 26.2.1 | Public Domain | [link](https://github.com/mk-fg/pretty-yaml) |
| pycparser | 3.0 | BSD-3-Clause | [link](https://github.com/eliben/pycparser) |
| pycryptodomex | 3.11.0 | Apache Software License; BSD License; Public Domain | [link](https://www.pycryptodome.org) |
| Pygments | 2.20.0 | BSD-2-Clause | [link](https://pygments.org) |
| pyliblo | 0.10.0 | LGPL | [link](http://das.nasophon.de/pyliblo/) |
| pyserial | 3.0 | BSD License | [link](https://github.com/pyserial/pyserial) |
| pystache | 0.5.4 | MIT License | [link](http://github.com/defunkt/pystache) |
| python-apt | 2.6.0 | GNU GPL | — |
| python-config | 0.1.2 | GNU General Public License v3 (GPLv3) | [link](https://github.com/KonishchevDmitry/python-config) |
| python-rtmidi | 1.5.8 | MIT License | [link](https://github.com/SpotlightKid/python-rtmidi) |
| PyYAML | 6.0.3 | MIT License | [link](https://pyyaml.org/) |
| requests | 2.28.1, 2.34.2 | Apache Software License | [link](https://requests.readthedocs.io) |
| rpi-lgpio | 0.6 | BSD License | [link](https://rpi-lgpio.readthedocs.io/) |
| scandir | 1.10.0 | BSD License | [link](https://github.com/benhoyt/scandir) |
| six | 1.16.0 | MIT License | [link](https://github.com/benjaminp/six) |
| smbus2 | 0.4.2 | MIT License | [link](https://github.com/kplindegaard/smbus2) |
| spidev | 3.5 | MIT License | [link](http://github.com/doceme/py-spidev) |
| ssh-import-id | 5.10 | GPLv3 | [link](https://launchpad.net/ssh-import-id) |
| tornado | 4.3 | Apache Software License | [link](http://www.tornadoweb.org/) |
| touchosc2midi | 0.0.12 | MIT License | [link](https://github.com/velolala/touchosc2midi) |
| unicategories | 0.1.2 | MIT License | [link](https://gitlab.com/ergoithz/unicategories) |
| urllib3 | 1.26.12 | MIT License | [link](https://urllib3.readthedocs.io/) |
| websockets | 16.0 | BSD-3-Clause | [link](https://github.com/python-websockets/websockets) |
| Werkzeug | 3.1.8 | BSD-3-Clause | [link](https://github.com/pallets/werkzeug/) |
| zeroconf | 0.47.3 | LGPL-2.1-or-later | [link](https://github.com/python-zeroconf/python-zeroconf) |

### Development / Build / Documentation Tools (not distributed at runtime)

<details>
<summary>Expand list</summary>

| Package | Version | License | Source |
|---|---|---|---|
| alabaster | 1.0.0 | BSD License | [link](https://alabaster.readthedocs.io/) |
| babel | 2.18.0 | BSD License | [link](https://babel.pocoo.org/) |
| coverage | 7.14.0 | Apache-2.0 | [link](https://github.com/coveragepy/coveragepy) |
| distlib | 0.3.6 | Python Software Foundation License | [link](https://bitbucket.org/pypa/distlib) |
| docopt | 0.6.2 | MIT License | [link](http://docopt.org) |
| docutils | 0.22.4 | BSD License; GNU General Public License (GPL); Public Domain | [link](https://docutils.sourceforge.io) |
| flake8 | 7.3.0 | MIT License | [link](https://github.com/pycqa/flake8) |
| imagesize | 2.0.0 | MIT License | [link](https://github.com/shibukawa/imagesize_py) |
| mccabe | 0.7.0 | MIT License | [link](https://github.com/pycqa/mccabe) |
| meson | 1.5.1 | Apache Software License | [link](https://mesonbuild.com) |
| pep8 | 1.7.1 | MIT License | [link](http://pep8.readthedocs.org/) |
| pycodestyle | 2.14.0 | MIT | [link](https://pycodestyle.pycqa.org/) |
| pyflakes | 3.4.0 | MIT License | [link](https://github.com/PyCQA/pyflakes) |
| roman-numerals | 4.1.0 | 0BSD OR CC0-1.0 | [link](https://github.com/AA-Turner/roman-numerals/blob/master/CHANGES.rst) |
| snowballstemmer | 3.1.0 | BSD-3-Clause | [link](https://github.com/snowballstem/snowball) |
| Sphinx | 9.0.4 | BSD-2-Clause | [link](https://www.sphinx-doc.org/) |
| sphinxcontrib-applehelp | 2.0.0 | BSD License | [link](https://www.sphinx-doc.org/) |
| sphinxcontrib-devhelp | 2.0.0 | BSD License | [link](https://www.sphinx-doc.org/) |
| sphinxcontrib-htmlhelp | 2.1.0 | BSD License | [link](https://www.sphinx-doc.org/) |
| sphinxcontrib-jsmath | 1.0.1 | BSD License | [link](http://sphinx-doc.org/) |
| sphinxcontrib-qthelp | 2.0.0 | BSD License | [link](https://www.sphinx-doc.org/) |
| sphinxcontrib-serializinghtml | 2.0.0 | BSD License | [link](https://www.sphinx-doc.org/) |
| toml | 0.10.2 | MIT License | [link](https://github.com/uiri/toml) |
| virtualenv | 20.17.1+ds | MIT License | [link](https://virtualenv.pypa.io/) |

</details>

---

## LV2 Audio Plugins


### Aida DSP

| Plugin | Version | License |
|--------|---------|---------|
| AIDA-X | 1.1 | http://spdx.org/licenses/GPL-3.0-or-later.html |

### Antanas Bruzas

| Plugin | Version | License |
|--------|---------|---------|
| abGate | 2.0 | LGPL |

### Artican

| Plugin | Version | License |
|--------|---------|---------|
| The Function | 2.0 | — |
| The Pilgrim | 2.0 | — |

 ### Aurelien Leblond
| Plugin | Version | License |
|--------|---------|---------|
| AMS VCF | 1.0 | isc |
| Granulator - Mono | 0.0 | isc |

### Bernhard Rusch

| Plugin | Version | License |
|--------|---------|---------|
| Molot Lite Mono | 0.1 | GPL |

### Blokas Labs
| Plugin | Version | License |
|--------|---------|---------|
| Invada Compressor (mono) | 2.1 | GPL v2 |
| Invada Test Tones | 2.1 | GPL v2 |

### Bollie

| Plugin | Version | License |
|--------|---------|---------|
| Bollie Delay | 2.6 | GPL |
| Bollie Delay XT | 0.1 | GPL |

### brummer

| Plugin | Version | License |
|--------|---------|---------|
| bluesbreaker | 1.0 | — |
| Neural Record | 1.3 | https://spdx.org/licenses/GPL-2.0-or-later |
| PowerAmpImpulses | 1.1 | — |
| PowerAmpTubes | 1.1 | — |
| PreAmpImpulses | 1.1 | — |
| PreAmpTubes | 1.1 | — |
| Ratatouille | 9.5 | https://spdx.org/licenses/BSD-3-Clause |
| Record-Mono | 2.2 | isc |
| Record-Mono Mini | 2.2 | isc |

### brummer10

| Plugin | Version | License |
|--------|---------|---------|
| CollisionDrive | 1.3 | — |
| FatFrog | 35.7 | isc |
| Harmonic Exciter | 1.0 | — |
| LittleFly | 35.0 | isc |
| MetalTone | 1.2 | — |
| Rumor | 1.2 | — |
| VintageAC30 | 1.0 | — |

### bx5a,romi1502

| Plugin | Version | License |
|--------|---------|---------|
| Mr. Freeze | 0.1 | GPL |

### Calf Studio Gear

| Plugin | Version | License |
|--------|---------|---------|
| Calf Gate | — | LGPL |

### Creative Intent

| Plugin | Version | License |
|--------|---------|---------|
| Temper | 5.0 | — |

### Damien Zammit

| Plugin | Version | License |
|--------|---------|---------|
| ZamAutoSat | 2.7 | GPL v2+ |
| ZaMaximX2 | 2.7 | GPL v2+ |
| ZamComp | 2.7 | GPL v2+ |
| ZamCompX2 | 2.7 | GPL v2+ |
| ZamDelay | 2.7 | GPL v2+ |
| ZamEQ2 | 2.7 | GPL v2+ |
| ZamGate | 2.7 | GPL v2+ |
| ZamGateX2 | 2.7 | GPL v2+ |
| ZamGEQ31 | 2.7 | GPL v2+ |
| ZamHeadX2 | 2.14 | GPL v2+ |
| ZamPhono | 2.14 | GPL v2+ |
| ZamTube | 2.7 | GPL v2+ |
| ZaMultiComp | 2.7 | GPL v2+ |
| ZaMultiCompX2 | 2.7 | GPL v2+ |
| ZamVerb | 2.14 | GPL v2+ |

### Datsounds

| Plugin | Version | License |
|--------|---------|---------|
| Obxd | 2.0 | — |

### David Robillard (FOMP)
| Plugin | Version | License |
|--------|---------|---------|
| 4-Band Parametric Filter | 0.0 | GPL-2.0 |
| CS Phaser 1 | 0.0 | GPL-2.0 |
| Moog High-Pass Filter 1 | 0.0 | GPL-2.0 |
| Moog Low-Pass Filter 1 | 0.0 | GPL-2.0 |
| Moog Low-Pass Filter 2 | 0.0 | GPL-2.0 |
| Moog Low-Pass Filter 3 | 0.0 | GPL-2.0 |
| Moog Low-Pass Filter 4 | 0.0 | GPL-2.0 |
| Pulse VCO | 0.0 | GPL-2.0 |
| Rec VCO | 0.0 | GPL-2.0 |
| reverb | 0.0 | GPL-2.0 |
| reverb-amb | 0.0 | GPL-2.0 |
| Saw VCO | 0.0 | GPL-2.0 |
| Square | 0.0 | GPL-2.0 |

### dcoredump

| Plugin | Version | License |
|--------|---------|---------|
| Dexed | 0.2 | GPL |

### devcurmudgeon
| Plugin | Version | License |
|--------|---------|---------|
| ALO | 0.9 | MIT |

### DISTRHO

| Plugin | Version | License |
|--------|---------|---------|
| 3 Band EQ | 2.0 | LGPL |
| 3 Band Splitter | 2.0 | LGPL |
| DIE Fluid Synth | 2.2 | GPL |
| MaBitcrush | 0.1 | ISC |
| MaFreeverb | 0.1 | ISC |
| MaGigaverb | 0.1 | ISC |
| MaPitchshift | 0.1 | ISC |
| Ping Pong Pan | 2.0 | LGPL |

### Dougal-s
| Plugin | Version | License |
|--------|---------|---------|
| Aether | 2.1 | MIT |

### dRowAudio

| Plugin | Version | License |
|--------|---------|---------|
| dRowAudio Tremolo | — | — |
| dRowAudio: Distortion | — | — |
| dRowAudio: Distortion Shaper | — | — |
| dRowAudio: Flanger | — | — |
| dRowAudio: Reverb | — | — |

### Edgar Lubicz

| Plugin | Version | License |
|--------|---------|---------|
| [SimSam](https://gitlab.com/edwillys/simsam) | 0.1 | GPL |

### falkTX

| Plugin | Version | License |
|--------|---------|---------|
| AirFont320 | 2.0 | LGPL |
| Audio Capture | 0.0 | AGPL-3.0 |
| Audio Gain (Mono) | 2.0 | GPLv2+ |
| Black Pearl 4A | 2.0 | LGPL |
| Black Pearl 4B | 2.0 | LGPL |
| Black Pearl 5 | 2.0 | LGPL |
| Fluid Bass | 2.0 | LGPL |
| Fluid Brass | 2.0 | LGPL |
| Fluid Chromatic Percussion | 2.0 | LGPL |
| Fluid Drums | 2.0 | LGPL |
| Fluid Ensemble | 2.0 | LGPL |
| Fluid Ethnic | 2.0 | LGPL |
| Fluid Guitars | 2.0 | LGPL |
| Fluid Organs | 2.0 | LGPL |
| Fluid Percussion | 2.0 | LGPL |
| Fluid Pianos | 2.0 | LGPL |
| Fluid Pipes | 2.0 | LGPL |
| Fluid Reeds | 2.0 | LGPL |
| Fluid SoundFX | 2.0 | LGPL |
| Fluid Strings | 2.0 | LGPL |
| Fluid SynthFX | 2.0 | LGPL |
| Fluid SynthLeads | 2.0 | LGPL |
| Fluid SynthPads | 2.0 | LGPL |
| FluidGM | 2.0 | LGPL |
| Kars | 2.1 | ISC |
| MIDI File | 150.22 | GPL-2.0 |
| Portal Sink | — | http://spdx.org/licenses/ISC.html |
| Rubberband (Mono) | 8.2 | GPL |

### geraldmwangi

| Plugin | Version | License |
|--------|---------|---------|
| Guitar Midi | 0.0 | LGPL |

### Guitarix team

| Plugin | Version | License |
|--------|---------|---------|
| Gx Studio Preamp Stereo | 28.3 | isc |
| GxAlembic | 28.3 | isc |
| GxAmplifier Stereo | 28.3 | isc |
| GxAmplifier-X | 28.3 | isc |
| GxAutoWah | 28.3 | isc |
| GxAxisFace | 34.0 | isc |
| GxBaJaTubeDriver | 35.0 | isc |
| GxBarkGraphicEQ | 28.3 | isc |
| GxBlueAmp | 35.0 | isc |
| GxBoobTube | 35.0 | isc |
| GxBooster | 28.3 | isc |
| GxBottleRocket | 34.0 | isc |
| GxCabinet | 28.3 | isc |
| GxChorus-Stereo | 28.3 | isc |
| GxClubDrive | 37.0 | isc |
| GxColorSoundTonebender | 28.3 | isc |
| GxCompressor | 28.3 | isc |
| GxCreamMachine | 34.0 | isc |
| GxCrybabyGCB95 | 28.3 | isc |
| GxDelay-Stereo | 28.3 | isc |
| GxDenoiser2 | 35.0 | isc |
| Gxdetune | 28.3 | isc |
| Gxdigital_delay | 28.3 | isc |
| Gxdigital_delay_st | 28.3 | isc |
| GxDistortionPlus | 36.0 | isc |
| GxDOP250 | 34.0 | isc |
| Gxduck_delay | 28.3 | isc |
| Gxduck_delay_st | 28.3 | isc |
| GxEcho-Stereo | 28.3 | isc |
| GxEpic | 35.0 | isc |
| GxEternity | 35.0 | isc |
| GxExpander | 28.3 | isc |
| GxFenderizer | 35.0 | isc |
| GxFlanger | 28.3 | isc |
| GxFuzz | 28.3 | isc |
| GxFuzzFaceFullerMod | 28.3 | isc |
| GxFuzzFaceJH-2 | 28.3 | isc |
| GxFuzzMaster | 28.3 | isc |
| GxFz1b | 34.0 | isc |
| GxFz1s | 34.0 | isc |
| GxGraphicEQ | 28.3 | isc |
| GxGuvnor | 28.3 | isc |
| GxHeathkit | 34.0 | isc |
| GxHighFrequencyBrightener | 28.3 | isc |
| GxHogsFoot | 28.3 | isc |
| GxHornet | 28.3 | isc |
| GxHotBox | 34.0 | isc |
| GxHyperion | 28.3 | isc |
| GxJCM800pre | 28.3 | isc |
| GxJCM800pre ST | 28.3 | isc |
| GxKnightFuzz | 34.0 | isc |
| GxLiquidDrive | 34.0 | isc |
| GxLuna | 35.0 | isc |
| GxMicroAmp | 34.0 | isc |
| GxMole | 28.3 | isc |
| GxMuff | 28.3 | isc |
| GxMultiBandCompressor | 28.3 | isc |
| GxMultiBandDelay | 28.3 | isc |
| GxMultiBandDistortion | 28.3 | isc |
| GxMultiBandEcho | 28.3 | isc |
| GxMultiBandReverb | 28.3 | isc |
| GxOC-2 | 28.3 | isc |
| GxOsMutantes | 28.3 | isc |
| GxOverDriver | 28.3 | isc |
| GxPhaser | 28.3 | isc |
| GxPlexi | 35.0 | isc |
| GxPushPull | 28.3 | isc |
| GxQuack | 34.0 | isc |
| GxRangemaster | 28.3 | isc |
| GxRedeye Vibro Chump | 28.3 | isc |
| GxReverb-Stereo | 28.3 | isc |
| Gxroom_simulator | 28.3 | isc |
| GxSaturator | 28.3 | isc |
| GxScreamingBird | 28.3 | isc |
| GxSD1 | 34.0 | isc |
| GxSD2Lead | 34.0 | isc |
| GxShakaTube | 35.0 | isc |
| Gxshimmizita | 28.3 | isc |
| GxSloopyBlue | 35.0 | isc |
| GxSlowGear | 34.0 | isc |
| GxSunFace | 34.0 | isc |
| GxSupersonic | 35.0 | isc |
| GxSuppaToneBender | 28.3 | isc |
| GxSustainer | 28.3 | isc |
| GxSVT | 34.0 | isc |
| Gxswitched_tremolo | 28.3 | isc |
| GxSwitchlessWah | 1.0 | isc |
| GxTiltTone | 28.3 | isc |
| GxTimRay | 35.0 | isc |
| GxToneMachine | 34.0 | isc |
| GxToneMender | 28.3 | isc |
| GxTremolo | 28.3 | isc |
| GxTubeDistortion | 35.0 | isc |
| GxTubeScreamer | 28.3 | isc |
| GxTubeTremelo | 28.3 | isc |
| GxTubeVibrato | 28.3 | isc |
| GxUltraCab | 35.0 | isc |
| GxUVox720k | 34.0 | isc |
| GxValveCaster | 38.1 | isc |
| GxVBassPreAmp | 34.0 | isc |
| GxVintageFuzzMaster | 28.4 | isc |
| GxVMK2 | 34.0 | isc |
| GxVoodooFuzz | 28.3 | isc |
| GxVoxTonebender | 28.3 | isc |
| GxWah | 28.3 | isc |
| GxWahwah | 28.3 | isc |
| GxZita_rev1-Stereo | 28.3 | isc |
| GxZoom | 34.0 | isc |
| XDarkTerror | 35.0 | isc |
| XTinyTerror | 35.0 | isc |

### GuitarML

| Plugin | Version | License |
|--------|---------|---------|
| TS-M1N3 | 2.1 | GPL-3.0 |

### Hannes Braun

| Plugin | Version | License |
|--------|---------|---------|
| Acceleration2 | 2.0 | MIT |
| ADClip7 | 2.0 | MIT |
| Baxandall | 2.0 | MIT |
| Capacitor | 2.0 | MIT |
| Capacitor2 | 2.0 | MIT |
| Channel8 | 2.0 | MIT |
| ClipOnly | 2.0 | MIT |
| ClipOnly2 | 2.0 | MIT |
| Console7Buss | 2.0 | MIT |
| Console7Cascade | 2.0 | MIT |
| Console7Channel | 2.0 | MIT |
| Console7Crunch | 2.0 | MIT |
| DeBess | 2.0 | MIT |
| Dyno | 2.0 | MIT |
| EdIsDim | 2.0 | MIT |
| EveryTrim | 2.0 | MIT |
| Galactic | 2.0 | MIT |
| Mackity | 2.0 | MIT |
| MidSide | 2.0 | MIT |
| Mojo | 2.0 | MIT |
| MV | 2.0 | MIT |
| Nikola | 2.0 | MIT |
| PocketVerbs | 2.0 | MIT |
| Pressure5 | 2.0 | MIT |
| Sidepass | 2.0 | MIT |
| Spiral | 2.0 | MIT |
| StarChild | 2.0 | MIT |
| Vibrato | 2.0 | MIT |

### Hanspeter Portner
| Plugin | Version | License |
|--------|---------|---------|
| Notes | 2.0 | Artistic-2.0 |

### Igor Brkic

| Plugin | Version | License |
|--------|---------|---------|
| VocProc | 0.2 | GPLv2 |

### J.Velcl@seznam.cz

| Plugin | Version | License |
|--------|---------|---------|
| WOW | 0.0 | — |

### Janos Buttgereit

| Plugin | Version | License |
|--------|---------|---------
| Schrammel OJD | 8.9 | GPL v3 |

### Jatin Chowdhury

| Plugin | Version | License |
|--------|---------|---------|
| ChowCentaur | 2.4 | BSD-3-Clause |

### Jean Pierre Cimalando

| Plugin | Version | License |
|--------|---------|---------|
| Rézonateur | 0.0 | http://spdx.org/licenses/BSL-1.0 |
| Rézonateur stereo | 0.0 | http://spdx.org/licenses/BSL-1.0 |
| String machine | 0.0 | http://spdx.org/licenses/GPL-2.0-or-later |
| String machine chorus | 0.0 | http://spdx.org/licenses/GPL-2.0-or-later |
| String machine stereo chorus | 0.0 | http://spdx.org/licenses/GPL-2.0-or-later |

### Lkjb

| Plugin | Version | License |
|--------|---------|---------|
| Luftikus | 1.2.1 | GPL v2 |
| ReFine | 2.1 | — |

### LSP LV2

| Plugin | Version | License |
|--------|---------|---------|
| LSP IR Mono | 0.2 | LGPL |

### Luciano Dato

| Plugin | Version | License |
|--------|---------|---------|
| Noise repellent | — | LGPL-3.0 |

### Martin Eastwood, falkTX

| Plugin | Version | License |
|--------|---------|---------|
| MVerb | 2.0 | GPL v3+ |

### Matt Tytel

| Plugin | Version | License |
|--------|---------|---------|
| Helm | v0.9.0 | GPL v3 |

### Mayank Sanganeria

| Plugin | Version | License |
|--------|---------|---------|
| Granulator | 1.0 | GPL |

### Micah John

| Plugin | Version | License |
|--------|---------|---------|
| Amp Profiler | — | GPL v3 |

### Michael Willis

| Plugin | Version | License |
|--------|---------|---------|
| Dragonfly Early Reflections | 4.6 | GPL-3.0 |
| Dragonfly Plate Reverb | 4.6 | GPL-3.0 |
| Dragonfly Room Reverb | 4.6 | GPL-3.0 |

### Michael Willis and Rob vd Berg

| Plugin | Version | License |
|--------|---------|---------|
| Dragonfly Hall Reverb | 4.6 | GPL-3.0 |

### Mike Oliphant

| Plugin | Version | License |
|--------|---------|---------|
| Neural Amp Modeler | 2.0 | GPL-3-0 |

### Milk Brewster

| Plugin | Version | License |
|--------|---------|---------|
| MIDI Gain | — | — |

### MOD

| Plugin | Version | License |
|--------|---------|---------|
| Arpeggiator | 1.2 | https://spdx.org/licenses/GPL-2.0-or-later |
| Attenuverter Booster | 3.0 | GPL v2+ |
| Audio to CV | 3.0 | — |
| AudioToCV Pitch | 2.0 | http://spdx.org/licenses/GPL-3.0-or-later.html |
| Cabinet Loader | 2.0 | http://spdx.org/licenses/ISC.html |
| Control to CV | 3.0 | GPL v2+ |
| Convolution Loader | 2.0 | http://spdx.org/licenses/ISC.html |
| CV ABS | 1.0 | GPL v2+ |
| CV Clock | 3.0 | GPL v2+ |
| CV Gate | 1.0 | GPL v2+ |
| CV meter | 1.0 | GPL v2+ |
| CV Parameter Modulation | 1.0 | GPL v2+ |
| CV Range Divider | 3.0 | GPL v2+ |
| CV Round | 1.0 | GPL v2+ |
| CV Switchbox 1-2 | 1.0 | GPL v2+ |
| CV Switchbox 1-3 | 1.0 | GPL v2+ |
| CV Switchbox 2-1 | 1.0 | GPL v2+ |
| CV Switchbox 3-1 | 1.0 | GPL v2+ |
| IR loader cabsim | 1.0 | isc |
| Logic Operators | 2.0 | GPL v2+ |
| MIDI SwitchBox 1-2 2C | 2.0 | GPLv2+ |
| MIDI SwitchBox 1-3 | 2.0 | GPLv2+ |
| MIDI SwitchBox 2-1 | 2.0 | GPLv2+ |
| MIDI SwitchBox 2-1 2C | 2.0 | GPLv2+ |
| MIDI SwitchBox 3-1 | 2.0 | GPLv2+ |
| MIDI to CV Poly | 1.1 | GPL v2+ |
| Mixer | 2.0 | GPLv3.0 |
| Mixer Stereo | 2.0 | GPLv3.0 |
| Random Generator | 1.0 | GPL v2+ |
| Slew Rate Limiter | 1.0 | GPL v2+ |
| Switchbox 1-2 ST | 1.1 | GPL v2+ |
| Switchbox 2-1 | 1.1 | GPL v2+ |
| Switchbox 2-1 ST | 1.1 | GPL v2+ |
| Volume | 1.0 | GPL v2+ |
| Volume 2x2 | 1.0 | GPL v2+ |

### MOD Devices

| Plugin | Version | License |
|--------|---------|---------|
| Compressor | 1.1 | http://spdx.org/licenses/ISC.html |
| Compressor Advanced | 1.1 | http://spdx.org/licenses/ISC.html |
| Noise Gate | 1.1 | http://spdx.org/licenses/ISC.html |
| Noise Gate Advanced | 1.1 | http://spdx.org/licenses/ISC.html |
| Noise Maker - ME | 1.1 | — |

### MOD Team

| Plugin | Version | License |
|--------|---------|---------|
| 2Voices | 0.4 | GPL |
| BandPassFilter | 0.0 | GPL |
| C* AmpVTS - Tube amp + Tone stack | 9.24 | GPL |
| C* AutoFilter | 9.24 | GPL |
| C* CabinetIII - Idealised loudspeaker cabinet emulation | 9.24 | GPL |
| C* CabinetIV - Idealised loudspeaker cabinet emulation | 9.24 | GPL |
| C* CEO - Chief Executive Oscillator | 9.24 | GPL |
| C* ChorusI - Mono chorus/flanger | 9.24 | GPL |
| C* Click - Metronome | 9.24 | GPL |
| C* Compress - Mono compressor | 9.24 | GPL |
| C* CompressX2 - Stereo compressor | 9.24 | GPL |
| C* Eq10 - 10-band equalizer | 9.24 | GPL |
| C* Eq10X2 - 10-band equalizer | 9.24 | GPL |
| C* Fractal - Audio stream from deterministic chaos | 9.24 | GPL |
| C* Narrower - Stereo image width reduction | 9.24 | GPL |
| C* Noisegate - Attenuate noise resident in silence | 9.24 | GPL |
| C* PhaserII - Mono phaser modulated by a Lorenz fractal | 9.24 | GPL |
| C* Plate - Versatile plate reverb | 9.24 | GPL |
| C* PlateX2 - Stereo in/out Versatile plate reverb | 9.24 | GPL |
| C* Saturate | 9.24 | GPL |
| C* Scape - Stereo delay + Filters | 9.24 | GPL |
| C* Sin - Sine wave generator | 9.24 | GPL |
| C* Spice | 9.24 | GPL |
| C* SpiceX2 | 9.24 | GPL |
| C* ToneStack - Tone stack emulation | 9.24 | GPL |
| C* White - White noise generator | 9.24 | GPL |
| C* Wider - Stereo image Synthesis | 9.24 | GPL |
| Capo | 0.4 | GPL |
| CrossOver 2 | 1.0 | GPL |
| CrossOver 3 | 1.0 | GPL |
| Drop | 0.2 | GPL |
| DS1 | 0.0 | GPL |
| Gain | 1.0 | GPL |
| Gain 2x2 | 1.0 | GPL |
| Harmonizer | — | GPL |
| Harmonizer2 | — | GPL |
| HarmonizerCS | — | GPL |
| HighPassFilter | 0.0 | GPL |
| LowPassFilter | 0.0 | GPL |
| MDA Ambience | 0.3 | GPL |
| MDA Bandisto | 0.5 | GPL |
| MDA BeatBox | 0.2 | GPL |
| MDA Combo | 0.4 | GPL |
| MDA De-ess | 0.2 | GPL |
| MDA Degrade | 0.2 | GPL |
| MDA Delay | 0.4 | GPL |
| MDA Detune | 0.4 | GPL |
| MDA Dither | 0.2 | GPL |
| MDA DubDelay | 0.7 | GPL |
| MDA DX10 | 0.3 | GPL |
| MDA Dynamics | 0.2 | GPL |
| MDA ePiano | 0.4 | GPL |
| MDA Image | 0.3 | GPL |
| MDA JX10 | 0.2 | GPL |
| MDA Leslie | 0.3 | GPL |
| MDA Limiter | 0.2 | GPL |
| MDA Loudness | 0.1 | GPL |
| MDA MultiBand | 0.3 | GPL |
| MDA Overdrive | 0.4 | GPL |
| MDA Piano | 0.1 | GPL |
| MDA RePsycho! | 0.1 | GPL |
| MDA RezFilter | 0.1 | GPL |
| MDA RingMod | 0.2 | GPL |
| MDA RoundPan | 0.2 | GPL |
| MDA Shepard | 0.4 | GPL |
| MDA Splitter | 0.2 | GPL |
| MDA Stereo | 0.2 | GPL |
| MDA SubSynth | 0.3 | GPL |
| MDA TalkBox | 0.2 | GPL |
| MDA TestTone | 0.2 | GPL |
| MDA ThruZero | 0.3 | GPL |
| MDA Transient | 0.1 | GPL |
| MDA VocInput | 0.2 | GPL |
| MDA Vocoder | 0.4 | GPL |
| MIDI SwitchBox 1-2 | 2.0 | GPLv2+ |
| MIDI to CV mono | 3.1 | — |
| Open Big Muff | 0.0 | GPL |
| Peak To CC | 0.0 | GPLv2+ |
| SooperLooper | 0.9 | GPL |
| SooperLooper 2x2 | 0.9 | GPL |
| Super Capo | — | GPL |
| Super Whammy | — | GPL |
| Switchbox 1-2 | 1.1 | GPL |
| SwitchTrigger4 | 1.1 | GPL |
| TAP AutoPanner | 7.2 | GPL |
| TAP Chorus/Flanger | 7.2 | GPL |
| TAP DeEsser | 7.2 | GPL |
| TAP Equalizer | 7.2 | GPL |
| TAP Equalizer/BW | 7.2 | GPL |
| TAP Fractal Doubler | 7.2 | GPL |
| TAP Mono Dynamics | 7.2 | GPL |
| TAP Pink/Fractal Noise | 7.2 | GPL |
| TAP Pitch Shifter | 7.2 | GPL |
| TAP Reflector | 7.3 | GPL |
| TAP Reverberator | 7.2 | GPL |
| TAP Rotary Speaker | 7.3 | GPL |
| TAP Scaling Limiter | 7.2 | GPL |
| TAP Sigmoid Booster | 7.2 | GPL |
| TAP Stereo Dynamics | 7.2 | GPL |
| TAP Stereo Echo | 7.3 | GPL |
| TAP Tremolo | 7.3 | GPL |
| TAP Tubewarmth | 7.2 | GPL |
| TAP Vibrato | 7.2 | GPL |
| ToggleSwitch | 1.1 | GPL |

### ndc Plugs

| Plugin | Version | License |
|--------|---------|---------|
| Amplitude Imposer | 0.1 | MIT |
| Cycle Shifter | 0.1 | MIT |
| Soul Force | 0.1 | MIT |

### Nedko Arnaudov

| Plugin | Version | License |
|--------|---------|---------|
| Vocoder | — | GPL |

### Nick Bailey
| Plugin | Version | License |
|--------|---------|---------|
| Triceratops | 0.0 | GPL-3.0 |

### Nick Dowell

| Plugin | Version | License |
|--------|---------|---------|
| amsynth | 1.5 | GPL |

### OpenAV

| Plugin | Version | License |
|--------|---------|---------|
| Bitta | 2.0 | GPL v2 |
| Filta | 2.0 | GPL |
| Sorcer | 2.0 | GPL v3 |

### Paul Ferrand

| Plugin | Version | License |
|--------|---------|---------|
| batteur | 1.0 | https://spdx.org/licenses/ISC |

### Pjotr Lasschuit

| Plugin | Version | License |
|--------|---------|---------|
| [Freakclip](https://github.com/pjotrompet) | 1.2 | GPL |
| [Freaktail](https://github.com/pjotrompet) | 1.0 | GPL |
| [Prefreak](https://github.com/pjotrompet) | 0.1 | GPL |

### Plainweave Software

| Plugin | Version | License |
|--------|---------|---------|
| JuceOPL | 2.0 | — |

### Rakarrack Team

| Plugin | Version | License |
|--------|---------|---------|
| rkr AlienWah | 0.0 | GPL v2 |
| rkr Analog Phaser | 0.0 | GPL v2 |
| rkr Arpie | 0.0 | GPL v2 |
| rkr Cabinet | 0.0 | GPL v2 |
| rkr Coil Crafter | 0.0 | GPL v2 |
| rkr CompBand | 0.0 | GPL v2 |
| rkr Compressor | 0.0 | GPL v2 |
| rkr Derelict | 0.0 | GPL v2 |
| rkr Distortion | 0.0 | GPL v2 |
| rkr DistBand | 0.0 | GPL v2 |
| rkr Dual Flange | 0.0 | GPL v2 |
| rkr EQ | 0.0 | GPL v2 |
| rkr Echo | 0.0 | GPL v2 |
| rkr Echotron | 0.0 | GPL v2 |
| rkr Echoverse | 0.0 | GPL v2 |
| rkr Exciter | 0.0 | GPL v2 |
| rkr Expander | 0.0 | GPL v2 |
| rkr Flanger/Chorus | 0.0 | GPL v2 |
| rkr Harmonizer (no midi) | 0.0 | GPL v2 |
| rkr Infinity | 0.0 | GPL v2 |
| rkr MuTroMojo | 0.0 | GPL v2 |
| rkr Musical Delay | 0.0 | GPL v2 |
| rkr OpticalTrem | 0.0 | GPL v2 |
| rkr Parametric EQ | 0.0 | GPL v2 |
| rkr Reverb | 0.0 | GPL v2 |
| rkr Shelf Boost | 0.0 | GPL v2 |
| rkr Shuffle | 0.0 | GPL v2 |
| rkr StereoHarmonizer (no midi) | 0.0 | GPL v2 |
| rkr StompBox | 0.0 | GPL v2 |
| rkr Sustainer | 0.0 | GPL v2 |
| rkr Synthfilter | 0.0 | GPL v2 |
| rkr Valve | 0.0 | GPL v2 |
| rkr VaryBand | 0.0 | GPL v2 |
| rkr Vibe | 0.0 | GPL v2 |
| rkr Vocoder | 0.0 | GPL v2 |
| rkr WahWah | 0.0 | GPL v2 |

### remaincalm.org

| Plugin | Version | License |
|--------|---------|---------|
| avocado | 2.0 | LGPL3 |
| floaty | 2.0 | LGPL3 |
| mud | 2.0 | LGPL3 |
| paranoia | 2.0 | LGPL3 |

### Resonant DSP

| Plugin | Version | License |
|--------|---------|---------|
| Swanky Amp | 2.4 | — |

### Robin Gareus

| Plugin | Version | License |
|--------|---------|---------|
| Instrument Tuner | 0.0 | GPL |
| Level Meter | 0.0 | GPL |
| MIDI Chord | 1033.31 | GPL |
| MIDI Clock Generator | 0.0 | GPL |
| MIDI Generator | 512.0 | GPL |
| MIDI Step Sequencer16x8 | 777.5 | GPL |
| MIDI Step Sequencer32x8 | 777.5 | GPL |
| MIDI Step Sequencer8x16 | 777.5 | GPL |
| MIDI Step Sequencer8x4 | 777.5 | GPL |
| MIDI Step Sequencer8x8 | 777.5 | GPL |
| MIDI Timecode (MTC) Generator | 0.0 | GPL |
| No Delay Line | 514.0 | GPL |
| setBfree DSP Tonewheel Organ | 2058.0 | GPL |
| setBfree Organ Overdrive | 2058.0 | GPL |
| setBfree Organ Reverb | 2058.0 | GPL |
| setBfree Whirl Speaker | 2058.0 | GPL |
| setBfree Whirl Speaker (Old version) | 2058.0 | GPL |
| setBfree Whirl Speaker - Extended Version | 2058.0 | GPL |
| Spectrum Analyzer | 517.21 | GPL |
| Stereo Balance Control | 1538.0 | GPL |
| Stereo X-Fade | 516.0 | GPL |
| TinyGain Mono | 770.0 | GPL |
| x42-Autotune | 2049.11 | GPL |
| x42-eq - Parametric Equalizer Mono | 1.1 | GPL |

### Sean Bolton, falkTX

| Plugin | Version | License |
|--------|---------|---------|
| Nekobi | 2.1 | GPL v2+ |

### sensorium

| Plugin | Version | License |
|--------|---------|---------|
| TheCloud | 0.1 | GPL3 |

### SHIRO

| Plugin | Version | License |
|--------|---------|---------|
| Harmless | 2.0 | ISC |
| Larynx | 2.0 | ISC |
| Modulay | 2.0 | ISC |
| Pitchotto | 2.0 | ISC |
| Shiroverb | 2.0 | ISC |

### Spencer Jackson

| Plugin | Version | License |
|--------|---------|---------|
| the infamous bent delay | 0.1 | GPL-2.0 |
| the infamous ewham | 0.1 | GPL-2.0 |
| the infamous Hip2B | 0.1 | GPL-2.0 |
| the infamous mindi | 0.1 | GPL-2.0 |
| the infamous power cut | 0.1 | GPL-2.0 |
| the infamous stuck | 0.1 | GPL-2.0 |

### Steve Harris

| Plugin | Version | License |
|--------|---------|---------|
| AM pitchshifter | — | GPL |
| Bode frequency shifter | — | GPL |
| Comb delay line, noninterpolating | — | GPL |
| Crossover distortion | — | GPL |
| Decimator | — | GPL |
| Gate | — | GPL |
| Glame Bandpass Analog Filter | — | GPL |
| Glame Bandpass Filter | — | GPL |
| GLAME Butterworth Lowpass | — | GPL |
| GVerb | — | GPL |
| Karaoke | — | GPL |
| Multivoice Chorus | — | GPL |
| Reverse Delay | — | GPL |
| Ringmod with LFO | — | GPL |
| SC1 | — | GPL |
| State Variable Filter | — | GPL |
| Tape Delay Simulation | — | GPL |
| Valve saturation | — | GPL |

### TAL

| Plugin | Version | License |
|--------|---------|---------|
| TAL-Reverb-II | — | — |

### TAL-Togu Audio Line

| Plugin | Version | License |
|--------|---------|---------|
| Tal-Dub-3 | — | — |
| Tal-Filter | — | — |
| Tal-Filter-2 | — | — |
| Tal-Reverb | — | — |
| Tal-Reverb-III | — | — |
| Tal-Vocoder-II | — | — |

### tumbetoene

| Plugin | Version | License |
|--------|---------|---------|
| Wolpertinger | 33.0 | — |

### VeJa plugins

| Plugin | Version | License |
|--------|---------|---------|
| Bass Cabinets | 1.0 | — |

### VeJa Plugins

| Plugin | Version | License |
|--------|---------|---------|
| British 1960A | 1.0 | — |
| Cabinet | 1.1 | — |
| Compressor | 1.1 | — |

### Vitling

| Plugin | Version | License |
|--------|---------|---------|
| Crypt | 0.3 | GPL v3 |

### ZynAddSubFX Team

| Plugin | Version | License |
|--------|---------|---------|
| ZynAddSubFX | 7.6 | GPL v2 |
| ZynAlienWah | 7.0 | GPL v2 |
| ZynChorus | 7.0 | GPL v2 |
| ZynDistortion | 7.0 | GPL v2 |
| ZynDynamicFilter | 7.0 | GPL v2 |
| ZynEcho | 7.0 | GPL v2 |
| ZynPhaser | 7.0 | GPL v2 |
| ZynReverb | 7.0 | GPL v2 |

### Unknown / Unattributed
| Plugin | Version | License |
|--------|---------|---------|
| Analogue Oscillator | — | GPL |
| Delayorama | — | GPL |
| DIE Compressor | 2.2 | GPL |
| DIE Delay | 4.2 | GPL v2+ |
| DIE EQ | 2.2 | GPL v2+ |
| DIE Expander | 2.2 | GPL |
| DIE Reverb | 2.4 | GPL |
| Loopor | — | isc |
| MIDI display | 1.0 | GPLv3+ |

---