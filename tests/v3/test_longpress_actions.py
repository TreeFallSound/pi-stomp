"""Mapping-form `longpress:` actions (PLAN.md): raw-CC toggle, specific/next
snapshot, and prev/next pedalboard within a bank.

The mapping form (`longpress: {midi_CC: 64}`, `{preset: 2}`, `{pedalboard: UP}`)
rows a single LONGPRESS decl alongside whatever PRESS action the footswitch
already carries. It's exclusive with the chord string/list form.
"""

from rtmidi.midiconstants import CONTROL_CHANGE

from common.contexts import (
    ControlClass,
    EventKind,
    PresetEffect,
    RawMidiCcEffect,
)
from pistomp.footswitch import Footswitch
from pistomp.input.event import SwitchEvent, SwitchEventKind
from tests.types import SystemFixture


def _fs_key(fs: Footswitch) -> str:
    if fs.midi_CC is not None:
        return f"{fs.midi_channel}:{fs.midi_CC}"
    return f"fs:{fs.id}"


def _longpress_rows(handler, key):
    rows = handler._controller_manager.effective_table.layers[0].rows.get(
        (ControlClass.FOOTSWITCH, EventKind.LONGPRESS), []
    )
    return [r for r in rows if r.control.id == key]


# ---------------------------------------------------------------------------
# Feature 1: raw-CC longpress
# ---------------------------------------------------------------------------


def test_longpress_raw_midi_cc(v3_system: SystemFixture):
    handler = v3_system.handler
    fs = v3_system.hw.footswitches[0]
    fs.add_preset(direction="UP")
    fs.longpress_action = {"midi_CC": 64}
    handler.bind_current_pedalboard()

    rows = _longpress_rows(handler, _fs_key(fs))
    assert len(rows) == 1
    effs = [e for e in rows[0].effects if isinstance(e, RawMidiCcEffect)]
    assert len(effs) == 1 and effs[0].cc == 64 and effs[0].channel == fs.midi_channel

    fs.toggled = False
    v3_system.hw.midiout.send_message.reset_mock()
    event = SwitchEvent(controller=fs, kind=SwitchEventKind.LONGPRESS, timestamp=1.0)

    handler.handle(event)
    v3_system.hw.midiout.send_message.assert_called_with([fs.midi_channel | CONTROL_CHANGE, 64, 127])
    assert fs.toggled is False  # LED stays in its PRESS role

    handler.handle(event)
    v3_system.hw.midiout.send_message.assert_called_with([fs.midi_channel | CONTROL_CHANGE, 64, 0])


def test_longpress_raw_midi_cc_drift_self_corrects(v3_system: SystemFixture):
    handler = v3_system.handler
    fs = v3_system.hw.footswitches[0]
    fs.longpress_action = {"midi_CC": 64}
    handler.bind_current_pedalboard()

    event = SwitchEvent(controller=fs, kind=SwitchEventKind.LONGPRESS, timestamp=1.0)
    sends = v3_system.hw.midiout.send_message

    sends.reset_mock()
    handler.handle(event)  # 127
    handler.handle(event)  # 0
    assert sends.call_args_list[0][0][0][2] == 127
    assert sends.call_args_list[1][0][0][2] == 0

    # A web-UI toggle can't touch our flywheel dict; the next press resumes on.
    handler.handle(event)
    assert sends.call_args_list[2][0][0][2] == 127


# ---------------------------------------------------------------------------
# Feature 2: longpress snapshot
# ---------------------------------------------------------------------------


def test_longpress_snapshot_specific_index(v3_system: SystemFixture, monkeypatch):
    handler = v3_system.handler
    fs = v3_system.hw.footswitches[0]
    fs.longpress_action = {"preset": 2}
    handler.bind_current_pedalboard()

    rows = _longpress_rows(handler, _fs_key(fs))
    assert any(isinstance(e, PresetEffect) and e.direction == "2" for e in rows[0].effects)

    called: list[int] = []
    monkeypatch.setattr(handler, "preset_set_and_change", lambda i: called.append(i))
    handler.handle(SwitchEvent(controller=fs, kind=SwitchEventKind.LONGPRESS, timestamp=1.0))
    assert called == [2]


def test_longpress_snapshot_up_down(v3_system: SystemFixture):
    handler = v3_system.handler
    hw = v3_system.hw

    fs_up = hw.footswitches[0]
    fs_up.longpress_action = {"preset": "UP"}
    fs_dn = hw.footswitches[1]
    fs_dn.longpress_action = {"preset": "DOWN"}
    handler.bind_current_pedalboard()

    calls: list[str] = []
    handler.preset_incr_and_change = lambda *a: calls.append("incr")
    handler.preset_decr_and_change = lambda *a: calls.append("decr")

    handler.handle(SwitchEvent(controller=fs_up, kind=SwitchEventKind.LONGPRESS, timestamp=1.0))
    handler.handle(SwitchEvent(controller=fs_dn, kind=SwitchEventKind.LONGPRESS, timestamp=2.0))
    assert calls == ["incr", "decr"]


# ---------------------------------------------------------------------------
# Feature 3: pedalboard scroll
# ---------------------------------------------------------------------------


def _spy_pedalboard_change(handler):
    changed: list = []
    handler.pedalboard_change = lambda pb: changed.append(pb)
    return changed


def test_pedalboard_incr_in_bank(v3_system: SystemFixture):
    handler = v3_system.handler
    pbs = handler.pedalboard_list
    assert len(pbs) >= 2
    handler.current_bank = "MyBank"
    handler.banks = {"MyBank": [p.title for p in pbs]}
    handler.set_current_pedalboard(pbs[0])

    changed = _spy_pedalboard_change(handler)
    handler.next_pedalboard()
    assert changed == [pbs[1]]


def test_pedalboard_wrap_at_bank_end(v3_system: SystemFixture):
    handler = v3_system.handler
    pbs = handler.pedalboard_list
    handler.current_bank = "MyBank"
    handler.banks = {"MyBank": [p.title for p in pbs]}
    handler.set_current_pedalboard(pbs[-1])

    changed = _spy_pedalboard_change(handler)
    handler.next_pedalboard()
    assert changed == [pbs[0]]


def test_pedalboard_wrap_at_bank_start(v3_system: SystemFixture):
    handler = v3_system.handler
    pbs = handler.pedalboard_list
    handler.current_bank = "MyBank"
    handler.banks = {"MyBank": [p.title for p in pbs]}
    handler.set_current_pedalboard(pbs[0])

    changed = _spy_pedalboard_change(handler)
    handler.previous_pedalboard()
    assert changed == [pbs[-1]]


def test_pedalboard_nav_no_bank(v3_system: SystemFixture):
    handler = v3_system.handler
    pbs = handler.pedalboard_list
    handler.current_bank = None
    handler.set_current_pedalboard(pbs[0])

    changed = _spy_pedalboard_change(handler)
    handler.next_pedalboard()
    assert changed == [pbs[1]]


def test_pedalboard_nav_single_pedalboard_bank(v3_system: SystemFixture):
    handler = v3_system.handler
    pbs = handler.pedalboard_list
    handler.current_bank = "Solo"
    handler.banks = {"Solo": [pbs[0].title]}
    handler.set_current_pedalboard(pbs[0])

    changed = _spy_pedalboard_change(handler)
    handler.next_pedalboard()
    handler.previous_pedalboard()
    assert changed == [pbs[0], pbs[0]]


# ---------------------------------------------------------------------------
# Chord form still works
# ---------------------------------------------------------------------------


def test_longpress_chord_form_still_works(v3_system: SystemFixture):
    fs = v3_system.hw.footswitches[0]
    fs.set_longpress_groups("next_snapshot")
    assert fs.longpress_groups == ["next_snapshot"]
    assert fs.longpress_action is None

    fs.set_longpress_groups(["next_snapshot", "toggle_bypass"])
    assert fs.longpress_groups == ["next_snapshot", "toggle_bypass"]
    assert fs.longpress_action is None

    fs.set_longpress_groups({"midi_CC": 64})
    assert fs.longpress_groups == []
    assert fs.longpress_action == {"midi_CC": 64}
