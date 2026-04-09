# Changelog
Notable user visible changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [v3.0.4] - 2026-04-09
### Added
- Add GUIDE.md for developer documentation
- Add pyproject.toml and uv.lock for local development tooling

### Fixed
- Sync current state of analog controls on pedalboard load
- Fix loading of plugins dependent on old version of fluidsynth lib (Calf, FluidGM, BlackPearl, etc.)
- Improved handling of tweak encoders (only pop main panel if encoder pressed)

### Changed
- Change reverb on NAM pedalboard to avoid crazy loading noise burst
- Attempt to normalize volumes accross pedalboards
- Prevent multiple USB audio devices from taking over index=0
- Many pi-gen-pistomp improvements for building the OS

## [v3.0.3] - 2025-12-12
### Changed
- Improved ALSA settings to better handle hot guitar pickups

### Fixed
- Fixed shutdown action display of red pi-Stomp splash screen

## [v3.0.2] - 2025-11-05
### Added
- Add system dianostics to System Info page: SystemState, Temp, Throttled

### Fixed
- try/except with warning when LED color can't be changed (RP1 issues, etc.)
- Calculate number of minimum analog controls based on hardware version

## [v3.0.0] - 2025-10-23
### Added
- Use PIO neopixel to allow WS28 support on pi5
- Add pi5 Eeprom update script

### Changed
- Change default longpress and tap tempo assignments

### Fixed
- Fix display of analog assignments
- Fix wifi config function

## [v2.3.0-beta.1] - 2024-10-03
### Added
- Pre-built software installation
- Support for v3 hardware
- New LCD UI (v3 and v2 hardware)
- New access to global EQ (v3 and v2 hardware)
- Patchstorage for plugin management (discovery, download, install)
- Filemanager for uploading audio files, MIDI, Impulse Response, Instruments and Amp Models (eg. NAM, Aida)
- Support for tap-tempo (v3 and v2 hardware)
- Support for most all common tasks via LCD/MOD-UI (ssh not required, v3 and v2 hardware)
- Support for Pedalboard Banks (v3 and v2 hardware)
- Support for alternate footswitch actions: longpress, multi-switch (v3 and v2 hardware)
- Support for additional plugin parameter types: log, enum, bool (v3 and v2 hardware)
- Support for assignable (multi-color) LED indicators (v3 hardware only)
- Ability to update (stash and pull) sample pedalboards via git
 
### Changed
- Upgrade to RPi bookworm OS
- Upgrade to python 3.11.1
- Upgrade to MOD v1.13
- Upgrade Real-time Kernel to 6.1.54
- Switched to using Network Manager for network management
- Switched to using gpiozero instead of RPi.GPIO (for future pi5 compatibility)
- Added hardware config file (default_config.yml) validation via schema

### Fixed
- User data backup/restore to USB
- Display current Snapshot name when not Default

## [v2.1.1]
### Added
- updates for amp profiler file handling

### Fixed
- Persist of plugin presets ([Issue #55](https://github.com/TreeFallSound/pi-stomp/issues/55))
- IQAudio card 48khz fix

## [v2.1.0]
### Added
- 64-bit OS (Raspbian Lite, no longer patchboxOS)
- Realtime Kernel
- Allow footswitch to be assigned to a specific snapshot index ([Issue #35](https://github.com/TreeFallSound/pi-stomp/issues/35))

## [v2.0.2]
Last supported 32-bit patchboxOS based software
### Changed
- Improved sync of LCD with pedalboard changed made via MOD
- WiFi performance improvements
- Alternative audio card support
- Reduce memory reserved for HDMI ([Issue #30](https://github.com/TreeFallSound/pi-stomp/issues/30))
