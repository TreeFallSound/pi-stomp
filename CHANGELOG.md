# Changelog
Notable user visible changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [v3.2.0] - 2026-07-05
### Added
- Pedalboard signal-path routing: the main screen now derives the real plugin graph from MOD-UI and lays pedals out to reflect actual topology (linear chains, parallel splits, stereo chains, split/merge), instead of a flat list
- Live pedalboard editing: plugins added, removed, or rewired in MOD-UI now update pi-Stomp's on-screen routing graph and footswitch/control bindings immediately over WebSocket, without a full pedalboard reload
- Dedicated x42 (fil4) parametric EQ panel with a live frequency-response graph; select a band and use the encoders to tweak gain, frequency, and Q with the curve updating live
- Notes panel for pedalboard/plugin annotations, with `✎` prefix on the pedalboard grid
- New plugin panels: CAPS Noisegate, DISTRHO Compressor, Reverb (with mode seector), GX Cabinet
- More EQ plugin types (parametric, graphic, custom)
- Plugin panels can now render as non-fullscreen dialogs
- Footswitch preset switches show the snapshot name on the label and light the LCD indicator for the active snapshot
- NAM Capture panel: record amp/pedal reamp sweeps to train Neural Amp Modeler profiles, with live input/output level meters, clipping detection, and progress display
- External MIDI: route any control (footswitch, knob, expression pedal, encoder) to a real external MIDI device (e.g. Source Audio C4, Line 6 HX Stomp) via `midi_port:` config, with auto-detection by device name and automatic value sync to the external device on pedalboard load
- Long pedalboard/preset names and menu text that don't fit the LCD now scroll (ping-pong) instead of being truncated
- Recovery mode menu item in the system menu

### Changed
- Footswitches redesigned: bypass/active state shown with consistent "dot" indicators across all screens, keycap-style labels, and a recessed shrouded tray for better legibility
- Tap-tempo visual redesign
- Analytic rounded-rect rendering for plugin windows, dialogs, and the selection reticule
- Plugin window UI now consistent with menus; vertical centering for large dialogs
- NAM plugins get their own distinct "T3K" visual style, subtitle, and label
- Analog controls aligned to pedal columns
- Re-ordered system menu; most useful things up top
- More reliable clean shutdown on SIGTERM
- JACK clients now run as their own subprocess to ensure pi-Stomp never takes R/T priority

### Fixed
- Fix inverted Q factor in x42 EQ panel (thanks @maarthome!)
- Fix pedal layout overlapping
- (v3) Fix plugin panels not refreshing bypass on main screen
- Fix non-idempotent plugin tile renders
- Fix dirty corner invalidation
- Footswitch preset bindings no longer leak across pedalboard loads
- Ethernet Audio Interface dialog: stop rebuilding every 2s and on every button press, fixing unresponsive buttons and SPI-blit visual glitches
- Brighten disabled footswitch label text for legibility
- Ensure parameter menus never crash

## [v3.1.0] - 2026-06-20
### Added
- On-device (LCD) strobe tuner with mute (v3 hardware only). Defaults to longpress on footswitch C
- Sync LCD and MOD-UI using WebSocket bridge (replaces last.json polling)
- Blend mode for parameter blending between snapshots
- Optional autosync for one-time send of MIDI CCs to current analog positions
- New wifi menu with scanning, multiple saved networks and in-progress animation
- Configurable LCD SPI speed via system menu
- Unit and integration tests with test harness
- `deploy.sh` to deploy your local code to the device
- `update.sh` for git pull + uv sync on-device
- `./run_emulator.sh [v1|v2|v3]`; v3 default; requires [MOD Desktop](https://mod.audio/desktop/)

### Fixed
- Users can now enter spaces in the letter selector (used for wifi config)
- Reduced footswitch and encoder burst latency
- Fix pedalboard reload detection crash
- Fix analog endpoint clamping
- Fix WiFi open networks and hotspot switching
- Fix menu scrolling for long lists
- Various type safety and dependency fixes (pillow, numpy, pi deps)

### Changed
- Upgrade Neural Amp Modeler plugin to version 2.0 which includes support for A2 models (and quality scaling)
- Migrate dev dependencies to dependency-groups (uv)
- Add pyright type checking, ruff linting
- Move fonts to `fonts/` directory (DejaVu)

## [v3.0.5] - 2026-06-12
No functional changes relative to v3.0.4
Prior releases did not correctly declare AGPL-3.0 licensing in accordance with included components.
This release corrects that. We have superseded prior releases accordingly.

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
