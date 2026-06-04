"""End-to-end bootstrap of the emulator handler + hardware + window.

Catches wiring regressions in bootstrap_emulator (add_lcd, add_hardware,
set_window, load_banks, load_pedalboards, set_current_pedalboard,
system_info_load) without requiring MOD Desktop or a real MIDI device."""

from pathlib import Path

import pytest

from emulator.bootstrap import bootstrap_emulator

PROJECT_ROOT = str(Path(__file__).parent.parent.parent)


@pytest.mark.parametrize("version", ["emulator_v1", "emulator_v2", "emulator_v3"])
def test_bootstrap_wires_handler_hardware_and_window(emulator_env, version):
    handler, midiout = bootstrap_emulator(version, PROJECT_ROOT)

    assert midiout is None  # forced to fail in the fixture
    assert handler.hardware is not None
    assert handler.lcd is not None
    assert handler._window is not None  # pyright: ignore[reportAttributeAccessIssue]
    assert len(handler.hardware.footswitches) >= 1

    handler.hardware.cleanup()


def test_bootstrap_selects_first_pedalboard_when_last_json_missing(emulator_env):
    handler, _ = bootstrap_emulator("emulator_v3", PROJECT_ROOT)

    assert handler.current is not None  # pyright: ignore[reportAttributeAccessIssue]
    assert handler.current.pedalboard.title == "Emu Rig"  # pyright: ignore[reportAttributeAccessIssue]

    assert handler.hardware is not None
    handler.hardware.cleanup()
