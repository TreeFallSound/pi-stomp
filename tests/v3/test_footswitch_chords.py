"""Longpress chords end to end, using the config from the bug report.

Four footswitches, each carrying a solo action plus a shared pedalboard-change
chord. Presses are simulated by driving the AdcSwitch state the real
detector maintains, then dispatching the longpress the way the detector does.
"""

import pytest

import pistomp.switchstate as switchstate
from tests.types import SystemFixture

RELEASED = switchstate.Value.RELEASED
PRESSED = switchstate.Value.PRESSED
LONGPRESSED = switchstate.Value.LONGPRESSED

# Per footswitch slot: [solo action, chord action], verbatim from the report
# (with the next_pedalboad typo corrected).
_CONFIG = [
    ["previous_snapshot", "previous_pedalboard"],
    ["next_snapshot", "previous_pedalboard"],
    ["toggle_tuner_enable", "next_pedalboard"],
    ["toggle_tap_tempo_enable", "next_pedalboard"],
]


@pytest.fixture
def chords(v3_system: SystemFixture):
    """Apply the report's longpress config and spy on every callback.

    Mirrors what Hardware.reinit does after applying a pedalboard's config:
    rebuild the resolver against the callback map, then register each switch.
    """
    handler = v3_system.handler
    fired: list[str] = []
    handler.callbacks = {name: (lambda n=name: fired.append(n)) for name in handler.callbacks}

    handler.chord_helper.rebuild(handler.callbacks)
    for fs, groups in zip(v3_system.hw.footswitches, _CONFIG):
        fs.set_longpress_groups(groups)
        handler.chord_helper.register(fs)
    return fired


def _hold(fs):
    fs.adc_switch.state = PRESSED


def _release(fs, handler):
    """Lift a foot. The 10ms loop polls right after, which is what re-arms a
    spent chord group."""
    fs.adc_switch.state = RELEASED
    handler.chord_helper.poll()


def _mature(fs):
    """Deliver the longpress the way AdcSwitch.refresh does — state first,
    then the callback."""
    fs.adc_switch.state = LONGPRESSED
    fs._on_switch(LONGPRESSED, timestamp=1000.0)


def test_lone_longpress_fires_only_its_solo_action(v3_system: SystemFixture, chords):
    fs0 = v3_system.hw.footswitches[0]
    _hold(fs0)
    _mature(fs0)
    assert chords == ["previous_snapshot"]


def test_chord_fires_only_the_chord_action(v3_system: SystemFixture, chords):
    """The reported bug: stomping fs0+fs1 ran both solo actions as well as the
    chord. Only previous_pedalboard may fire."""
    fs0, fs1 = v3_system.hw.footswitches[0], v3_system.hw.footswitches[1]
    _hold(fs0)
    _hold(fs1)

    _mature(fs0)  # fs0 was pressed first, so it matures first
    _mature(fs1)  # ~50ms later

    assert chords == ["previous_pedalboard"]


def test_second_chord_pair_is_independent(v3_system: SystemFixture, chords):
    fs2, fs3 = v3_system.hw.footswitches[2], v3_system.hw.footswitches[3]
    _hold(fs2)
    _hold(fs3)
    _mature(fs2)
    _mature(fs3)
    assert chords == ["next_pedalboard"]


def test_chord_then_release_then_lone_stomp(v3_system: SystemFixture, chords):
    fs0, fs1 = v3_system.hw.footswitches[0], v3_system.hw.footswitches[1]
    _hold(fs0)
    _hold(fs1)
    _mature(fs0)
    _mature(fs1)
    _release(fs0, v3_system.handler)
    _release(fs1, v3_system.handler)

    _hold(fs1)
    _mature(fs1)
    assert chords == ["previous_pedalboard", "next_snapshot"]


def test_cross_pair_stomp_fires_both_solos(v3_system: SystemFixture, chords):
    """fs1 and fs2 share no group, so pressing them together is two lone
    longpresses, not a chord."""
    fs1, fs2 = v3_system.hw.footswitches[1], v3_system.hw.footswitches[2]
    _hold(fs1)
    _hold(fs2)
    _mature(fs1)
    _mature(fs2)
    assert chords == ["next_snapshot", "toggle_tuner_enable"]


def test_shipped_default_config_forms_the_pedalboard_chords(v3_system: SystemFixture):
    """Pins what setup/config_templates/default_config_pistomptre.yml ships —
    the fixture builds hardware straight from it, so this covers the real
    config-to-group path rather than the hand-built one above."""
    groups = {
        name: [m.id for m in group.members]
        for name, group in v3_system.handler.chord_helper.groups.items()
    }
    assert groups == {
        "previous_snapshot": [0],
        "previous_pedalboard": [0, 1],
        "next_snapshot": [1],
        "toggle_tuner_enable": [2],
        "next_pedalboard": [2, 3],
        "toggle_tap_tempo_enable": [3],
    }
