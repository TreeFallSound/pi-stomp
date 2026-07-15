"""Footswitch short-press and longpress dispatch through the binding table
(Stages 5-6).

The imperative if-chain in Handler._handle_footswitch is replaced on Modhandler
by a table resolve + _fire_row. Each footswitch action type — preset, taptempo,
midi_CC toggle, relay longpress, plugin-:bypass — is a binding row; the table
picks the winner and the fire arm owns the hardware side effects.
"""


from common.contexts import (
    ControlClass,
    EventKind,
    MidiCcEffect,
    ParamEffect,
    PresetEffect,
    RelayEffect,
    TapTempoEffect,
)
from common.parameter import BYPASS_SYMBOL
from pistomp.footswitch import Footswitch
from pistomp.input.event import SwitchEvent, SwitchEventKind
from tests.types import SystemFixture


def _fs_key(fs: Footswitch) -> str:
    if fs.midi_CC is not None:
        return f"{fs.midi_channel}:{fs.midi_CC}"
    return f"fs:{fs.id}"


# ---------------------------------------------------------------------------
# Stage 5: row construction
# ---------------------------------------------------------------------------


def test_midi_cc_toggle_footswitch_builds_press_row(v3_system: SystemFixture):
    """A footswitch with midi_CC and no plugin binding produces a
    MidiCcEffect(toggle=True) PRESS row."""
    handler = v3_system.handler
    handler.bind_current_pedalboard()

    fs0 = v3_system.hw.footswitches[0]
    assert fs0.midi_CC is not None
    key = _fs_key(fs0)

    rows = handler._controller_manager.effective_table.layers[0].rows.get(
        (ControlClass.FOOTSWITCH, EventKind.PRESS), []
    )
    by_id = {r.control.id: r for r in rows}
    assert key in by_id
    effects = [e for e in by_id[key].effects if isinstance(e, MidiCcEffect)]
    assert len(effects) == 1
    assert effects[0].toggle is True


def test_preset_footswitch_builds_preset_effect_row(v3_system: SystemFixture):
    """A preset footswitch produces a PresetEffect PRESS row."""
    handler = v3_system.handler
    fs = v3_system.hw.footswitches[0]
    fs.add_preset(callback=handler.preset_incr_and_change, direction="UP")
    handler.bind_current_pedalboard()

    key = _fs_key(fs)
    rows = handler._controller_manager.effective_table.layers[0].rows.get(
        (ControlClass.FOOTSWITCH, EventKind.PRESS), []
    )
    by_id = {r.control.id: r for r in rows}
    assert key in by_id
    effects = [e for e in by_id[key].effects if isinstance(e, PresetEffect)]
    assert len(effects) == 1
    assert effects[0].direction == "UP"


def test_taptempo_footswitch_builds_two_gated_rows(v3_system: SystemFixture):
    """A taptempo footswitch produces a TapTempoEffect row (enabled_when
    is_enabled) and a MidiCcEffect(toggle=True) row (enabled_when not
    is_enabled)."""
    handler = v3_system.handler
    handler.bind_current_pedalboard()

    # fs3 has taptempo in the default config
    fs3 = v3_system.hw.footswitches[3]
    assert fs3.taptempo is not None
    key = _fs_key(fs3)

    rows = handler._controller_manager.effective_table.layers[0].rows.get(
        (ControlClass.FOOTSWITCH, EventKind.PRESS), []
    )
    by_id = [r for r in rows if r.control.id == key]
    assert len(by_id) == 2

    tap_rows = [r for r in by_id if any(isinstance(e, TapTempoEffect) for e in r.effects)]
    cc_rows = [r for r in by_id if any(isinstance(e, MidiCcEffect) for e in r.effects)]
    assert len(tap_rows) == 1
    assert len(cc_rows) == 1
    assert tap_rows[0].enabled_when is not None
    assert cc_rows[0].enabled_when is not None


def test_plugin_bound_footswitch_has_param_effect_row(v3_system: SystemFixture, make_plugin):
    """A footswitch bound to a plugin :bypass gets a ParamEffect PRESS row from
    _bind_plugin_parameters, not a MidiCcEffect toggle row from
    _bind_footswitch_actions."""
    handler = v3_system.handler
    ch = v3_system.hw.midi_channel
    fs0 = v3_system.hw.footswitches[0]
    binding = f"{ch}:{fs0.midi_CC}"

    plugin = make_plugin("fuzz", has_footswitch=True)
    plugin.parameters[BYPASS_SYMBOL].binding = binding
    handler.current.pedalboard.plugins = [plugin]
    handler.bind_current_pedalboard()

    rows = handler._controller_manager.effective_table.layers[0].rows.get(
        (ControlClass.FOOTSWITCH, EventKind.PRESS), []
    )
    by_id = [r for r in rows if r.control.id == binding]
    assert len(by_id) == 1
    effects = [e for e in by_id[0].effects if isinstance(e, ParamEffect)]
    assert len(effects) == 1
    # No stale MidiCcEffect toggle row — _bind_footswitch_actions skipped this fs
    # because fs.parameter is not None.
    cc_effects = [e for e in by_id[0].effects if isinstance(e, MidiCcEffect)]
    assert len(cc_effects) == 0


def test_toggle_plugin_bypass_through_table_fires_param_effect(v3_system: SystemFixture, make_plugin):
    """toggle_plugin_bypass() on a footswitch-bound plugin routes through the
    Modhandler._handle_footswitch override → table → ParamEffect arm. With a
    properly built table (bind_current_pedalboard after setting the binding),
    the winner is the ParamEffect row, not a stale MidiCcEffect toggle row."""
    handler = v3_system.handler
    hw = v3_system.hw
    ch = hw.midi_channel
    fs0 = hw.footswitches[0]
    binding = f"{ch}:{fs0.midi_CC}"

    plugin = make_plugin("fuzz", has_footswitch=True)
    plugin.parameters[BYPASS_SYMBOL].binding = binding
    handler.current.pedalboard.plugins = [plugin]
    handler.bind_current_pedalboard()

    # The table has a ParamEffect row, not a MidiCcEffect row.
    rows = handler._controller_manager.effective_table.layers[0].rows.get(
        (ControlClass.FOOTSWITCH, EventKind.PRESS), []
    )
    param_rows = [r for r in rows if r.control.id == binding
                  and any(isinstance(e, ParamEffect) for e in r.effects)]
    assert len(param_rows) == 1

    hw.midiout.send_message.reset_mock()
    handler.toggle_plugin_bypass(plugin)

    hw.midiout.send_message.assert_called_once()
    sent_cc = hw.midiout.send_message.call_args[0][0]
    assert sent_cc[1] == fs0.midi_CC


# ---------------------------------------------------------------------------
# Stage 5: dispatch
# ---------------------------------------------------------------------------


def test_midi_cc_toggle_footswitch_press_emits_cc_and_toggles_led(v3_system: SystemFixture):
    """Short-press on a CC-toggle footswitch resolves the MidiCcEffect row,
    toggles fs.toggled, sets the LED, and emits the CC."""
    handler = v3_system.handler
    handler.bind_current_pedalboard()

    fs0 = v3_system.hw.footswitches[0]
    fs0.toggled = False
    _fs_key(fs0)

    event = SwitchEvent(controller=fs0, kind=SwitchEventKind.PRESS, timestamp=1000.0)
    assert handler.handle(event) is True

    assert fs0.toggled is True
    # midiout.send_message called with [channel|CONTROL_CHANGE, CC, 127]
    from rtmidi.midiconstants import CONTROL_CHANGE
    v3_system.hw.midiout.send_message.assert_called_with(
        [fs0.midi_channel | CONTROL_CHANGE, fs0.midi_CC, 127]
    )


def test_preset_footswitch_press_changes_preset(v3_system: SystemFixture):
    """Short-press on a preset footswitch resolves the PresetEffect row and
    calls the right preset method."""
    handler = v3_system.handler
    fs = v3_system.hw.footswitches[0]
    fs.add_preset(callback=handler.preset_incr_and_change, direction="UP")
    handler.bind_current_pedalboard()

    calls: list[str] = []
    original = handler.preset_incr_and_change
    handler.preset_incr_and_change = lambda *a: calls.append("incr")
       # Update the callback fs points to (add_preset captured the original bound method)
    fs.preset_callback = handler.preset_incr_and_change

    event = SwitchEvent(controller=fs, kind=SwitchEventKind.PRESS, timestamp=1000.0)
    assert handler.handle(event) is True
    assert calls == ["incr"]

    handler.preset_incr_and_change = original


def test_taptempo_footswitch_press_when_enabled_stamps(v3_system: SystemFixture):
    """Short-press on a taptempo footswitch (when enabled) resolves the
    TapTempoEffect row and stamps with the event timestamp."""
    handler = v3_system.handler
    handler.bind_current_pedalboard()

    fs3 = v3_system.hw.footswitches[3]
    assert fs3.taptempo is not None
    # Enable taptempo
    v3_system.hw.toggle_tap_tempo_enable(120)
    assert fs3.taptempo.is_enabled()

    stamped: list[float] = []
    original = fs3.taptempo.stamp
    fs3.taptempo.stamp = lambda t: stamped.append(t)

    event = SwitchEvent(controller=fs3, kind=SwitchEventKind.PRESS, timestamp=42.0)
    assert handler.handle(event) is True
    assert stamped == [42.0]

    fs3.taptempo.stamp = original


def test_taptempo_footswitch_press_when_disabled_emits_cc(v3_system: SystemFixture):
    """Short-press on a taptempo footswitch (when disabled) resolves the
    MidiCcEffect toggle row instead — the enabled_when gate on the TapTempoEffect
    row disables it, and the CC-toggle row wins."""
    handler = v3_system.handler
    handler.bind_current_pedalboard()

    fs3 = v3_system.hw.footswitches[3]
    assert fs3.taptempo is not None
    assert not fs3.taptempo.is_enabled()  # disabled by default
    fs3.toggled = False

    event = SwitchEvent(controller=fs3, kind=SwitchEventKind.PRESS, timestamp=1000.0)
    assert handler.handle(event) is True

    assert fs3.toggled is True  # CC toggle fired


def test_unbound_footswitch_press_does_nothing(v3_system: SystemFixture):
    """A footswitch with no action rows (no midi_CC, no preset, no taptempo)
    resolves nothing and does no harm."""
    handler = v3_system.handler
    fs = v3_system.hw.footswitches[0]
    fs.midi_CC = None
    fs.preset_direction = None
    fs.taptempo = None
    handler.bind_current_pedalboard()

    fs.toggled = False
    event = SwitchEvent(controller=fs, kind=SwitchEventKind.PRESS, timestamp=1000.0)
    assert handler.handle(event) is True
    assert fs.toggled is False


# ---------------------------------------------------------------------------
# Stage 6: relay longpress
# ---------------------------------------------------------------------------


class _FakeRelay:
    def __init__(self):
        self.enabled = False

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False

    def get(self):
        return self.enabled

    def update(self, val):
        self.enabled = val

    def init_state(self):
        return self.enabled


def test_relay_footswitch_longpress_toggles_relay(v3_system: SystemFixture):
    """A relay footswitch longpress resolves a RelayEffect row and toggles the
    relay, LED, and LCD bypass indicator."""
    handler = v3_system.handler
    fs = v3_system.hw.footswitches[0]
    relay = _FakeRelay()
    fs.add_relay(relay)
    handler.bind_current_pedalboard()

    key = _fs_key(fs)
    rows = handler._controller_manager.effective_table.layers[0].rows.get(
        (ControlClass.FOOTSWITCH, EventKind.LONGPRESS), []
    )
    by_id = [r for r in rows if r.control.id == key]
    assert len(by_id) == 1
    assert any(isinstance(e, RelayEffect) for e in by_id[0].effects)

    fs.toggled = False
    event = SwitchEvent(controller=fs, kind=SwitchEventKind.LONGPRESS, timestamp=1000.0)
    assert handler.handle(event) is True

    assert fs.toggled is True
    assert relay.get() is True


def test_chord_footswitch_longpress_falls_through_to_chord_helper(v3_system: SystemFixture):
    """A non-relay footswitch longpress (no RelayEffect row) falls through to
    chord_helper.observe — the documented exception that stays as code."""
    handler = v3_system.handler
    handler.bind_current_pedalboard()

    fs0 = v3_system.hw.footswitches[0]
    assert not fs0.relay_list  # no relay

    observed: list = []
    original = handler.chord_helper.observe
    handler.chord_helper.observe = lambda fs, timestamp: observed.append((fs, timestamp))

    event = SwitchEvent(controller=fs0, kind=SwitchEventKind.LONGPRESS, timestamp=99.0)
    assert handler.handle(event) is True
    assert len(observed) == 1
    assert observed[0][0] is fs0
    assert observed[0][1] == 99.0

    handler.chord_helper.observe = original


def test_relay_footswitch_short_press_still_toggles(v3_system: SystemFixture):
    """A relay footswitch also has a short-press action (CC toggle). The PRESS
    row resolves the CC toggle, the LONGPRESS row resolves the relay — both
    through the table."""
    handler = v3_system.handler
    fs = v3_system.hw.footswitches[0]
    relay = _FakeRelay()
    fs.add_relay(relay)
    handler.bind_current_pedalboard()

    # Short press → CC toggle (the relay footswitch still has midi_CC)
    fs.toggled = False
    event = SwitchEvent(controller=fs, kind=SwitchEventKind.PRESS, timestamp=1000.0)
    assert handler.handle(event) is True
    assert fs.toggled is True
    # Relay untouched by short press
    assert relay.get() is False


def test_bypass_config_on_relayless_hardware_is_ignored(v3_system: SystemFixture, tmp_path):
    """A v3 config with bypass: on relay-less hardware (Pistomptre) must not
    crash — the relay is None, so the config is ignored with a warning instead
    of calling add_relay(None) which would blow up on None.init_state()."""
    import yaml
    handler = v3_system.handler
    hw = v3_system.hw
    assert hw.relay is None  # v3 has no relay hardware

    bundle_dir = tmp_path / "bypass_rig.pedalboard"
    bundle_dir.mkdir()
    (bundle_dir / "config.yml").write_text(
        yaml.dump({"hardware": {"footswitches": [{"id": 0, "bypass": "LEFT_RIGHT"}]}})
    )
    pb = handler.pedalboards["/path/to/new.pedalboard"]
    pb.bundle = str(bundle_dir)
    pb.plugins = []

    handler.set_current_pedalboard(pb)

    fs0 = hw.footswitches[0]
    assert fs0.relay_list == []  # no relay added — config ignored, no crash