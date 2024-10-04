# Changelog
Notable user visible changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [v2.3.0-beta.1] - 2024-10-03
### Added
- Pre-built software installation
- Support for v3 hardware
- New LCD UI (v3 and v2 hardware)
- New access to global EQ (v3 and v2 hardware)
- Patchstorage for plugin management (discovery, download, install)
- Filemanager for uploading audio files, MIDI, Impulse Response, Instruments and Amp Models (eg. NAM, Aida)
- Support for tap-tempo
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