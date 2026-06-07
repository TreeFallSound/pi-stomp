"""Characterization of Mod.bind_current_pedalboard() (v1).

Pins behavior that differs from the v3 (modhandler) twin so a future shared
controller-manager extraction can't silently flatten the asymmetry:

  - v1 reorders the plugin chain so footswitch-controlled plugins sit last.
  - v1 populates analog_controllers from an AnalogMidiControl's cfg dict,
    stamping CATEGORY + TYPE (but, unlike v3, no ID).
"""

import common.token as Token
from pistomp.analogmidicontrol import AnalogMidiControl
from pistomp.footswitch import Footswitch


def _key_of(hw, predicate):
    return next(k for k, v in hw.controllers.items() if predicate(v))


def test_v1_bind_footswitch_and_analog(v1_system, make_plugin):
    handler = v1_system.handler
    hw = v1_system.hw

    fs_key = _key_of(hw, lambda c: isinstance(c, Footswitch))
    knob_key = _key_of(hw, lambda c: isinstance(c, AnalogMidiControl) and c.type == Token.KNOB)
    fs = hw.controllers[fs_key]
    knob = hw.controllers[knob_key]

    fuzz = make_plugin("fuzz", category="Distortion")
    fuzz.parameters[":bypass"].binding = fs_key
    tone = make_plugin("tone", category="Filter")
    tone.parameters[":bypass"].binding = knob_key

    handler.current.pedalboard.plugins = [fuzz, tone]
    handler.bind_current_pedalboard()

    # Footswitch bound to its plugin's bypass param; plugin flagged.
    assert fs.parameter is fuzz.parameters[":bypass"]
    assert fuzz.has_footswitch is True

    # Analog control surfaced in the LCD assignment dict with category + type.
    analog_entries = [
        cfg for cfg in handler.current.analog_controllers.values()
        if cfg.get(Token.TYPE) == Token.KNOB
    ]
    assert len(analog_entries) == 1
    entry = analog_entries[0]
    assert entry[Token.CATEGORY] == "Filter"
    # v1 does NOT stamp an ID onto the analog cfg (v3 does) — pin the difference.
    assert Token.ID not in entry


def test_v1_bind_reorders_footswitch_plugins_to_end(v1_system, make_plugin):
    """v1 moves footswitch-controlled plugins to the tail of the chain."""
    handler = v1_system.handler
    hw = v1_system.hw

    fs_key = _key_of(hw, lambda c: isinstance(c, Footswitch))

    fuzz = make_plugin("fuzz")          # footswitch-controlled
    fuzz.parameters[":bypass"].binding = fs_key
    reverb = make_plugin("reverb")      # no controller binding

    # Footswitch plugin deliberately placed first.
    handler.current.pedalboard.plugins = [fuzz, reverb]
    handler.bind_current_pedalboard()

    titles = [p.instance_id for p in handler.current.pedalboard.plugins]
    assert titles == ["reverb", "fuzz"], "footswitch plugin must be reordered to the end"
