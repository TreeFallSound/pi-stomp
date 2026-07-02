"""Footswitches mapped directly to a snapshot index (`preset: <int>` in config).

Covers four behaviors:
  1. The label shows the snapshot name, not the raw index.
  2. `Hardware.__init_footswitches` clears any midi_CC (default-config or
     override) when `preset:` is configured, since a preset footswitch's own
     press dispatch always short-circuits on preset_callback before ever
     reaching midi_CC emission (see Footswitch.pressed) -- an
     inherited-but-unused CC otherwise sits in `hw.controllers` where
     ControllerManager.bind() can match it against an unrelated plugin's
     MIDI-learned binding and steal fs.parameter.
  3. The label survives even if `fs.parameter` still ends up set by some
     other path -- defense in depth on top of (2), so
     `draw_footswitch`/`draw_unbound_footswitches`/`update_footswitch` never
     let a plugin/param name clobber a preset label.
  4. The footswitch's LED/indicator lights only when its mapped snapshot is
     the currently active one.
"""

import yaml
from unittest.mock import MagicMock

from common.parameter import Parameter
from tests.types import SystemFixture


def _plugin_param() -> Parameter:
    p = MagicMock(spec=Parameter)
    p.symbol = ":bypass"
    p.instance_id = "/Reverb"
    p.value = 0
    p.minimum = 0
    p.maximum = 1
    return p


class TestPresetFootswitchLabel:
    def test_shows_snapshot_name_not_index(self, v3_system: SystemFixture):
        handler = v3_system.handler
        fs = v3_system.hw.footswitches[0]
        fs.add_preset(callback=handler.preset_set_and_change, callback_arg=1)

        # v3_system's snapshot/list mock returns {"0": "Clean", "1": "Lead"}
        # (footswitch_label lowercases, same as it does for plugin names)
        assert handler.lcd.footswitch_label(fs) == "lead"

    def test_falls_back_to_index_when_name_unknown(self, v3_system: SystemFixture):
        handler = v3_system.handler
        fs = v3_system.hw.footswitches[0]
        fs.add_preset(callback=handler.preset_set_and_change, callback_arg=7)

        assert handler.lcd.footswitch_label(fs) == "7"


class TestPresetConfigClearsDefaultMidiCC:
    """Root-cause coverage: a footswitch config'd with `preset:` must lose any
    midi_CC (default-config or override) and drop out of hw.controllers, so it
    can never be matched by ControllerManager.bind() against an unrelated
    plugin's MIDI-learned parameter."""

    def test_preset_override_clears_inherited_default_midi_cc(self, v3_system: SystemFixture, tmp_path):
        handler = v3_system.handler
        hw = v3_system.hw
        # default_config_pistomptre.yml gives footswitch 1 midi_CC: 61 with no preset.
        fs1 = hw.footswitches[1]
        assert fs1.midi_CC == 61
        assert any(v is fs1 for v in hw.controllers.values())

        bundle_dir = tmp_path / "preset_rig.pedalboard"
        bundle_dir.mkdir()
        (bundle_dir / "config.yml").write_text(
            yaml.dump({"hardware": {"footswitches": [{"id": 1, "preset": 0}]}})
        )
        pb = handler.pedalboards["/path/to/new.pedalboard"]
        pb.bundle = str(bundle_dir)
        pb.plugins = []

        handler.set_current_pedalboard(pb)

        assert fs1.midi_CC is None
        assert all(v is not fs1 for v in hw.controllers.values())


class TestPresetFootswitchLabelSurvivesParameterBinding:
    def test_draw_unbound_footswitches_keeps_snapshot_label(self, v3_system: SystemFixture):
        handler = v3_system.handler
        hw = v3_system.hw
        lcd = handler.lcd
        fs = hw.footswitches[0]
        fs.add_preset(callback=handler.preset_set_and_change, callback_arg=0)
        fs.parameter = _plugin_param()  # defense-in-depth: simulates fs.parameter
        # getting set through some other path despite (2) above

        lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
        lcd.draw_main_panel()

        assert fs.get_display_label() == "clean"

    def test_update_footswitch_keeps_snapshot_label(self, v3_system: SystemFixture):
        handler = v3_system.handler
        hw = v3_system.hw
        lcd = handler.lcd
        fs = hw.footswitches[0]
        fs.add_preset(callback=handler.preset_set_and_change, callback_arg=0)

        lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
        lcd.draw_main_panel()

        fs.parameter = _plugin_param()  # bound after the fact (e.g. MIDI learn)
        lcd.update_footswitch(fs)

        assert fs.get_display_label() == "clean"


class TestPresetFootswitchIndicator:
    def test_active_snapshot_footswitch_drives_physical_led(self, v3_system: SystemFixture):
        """A press never touches fs.toggled for preset footswitches
        (Footswitch.pressed returns early on the preset_callback branch), so
        the LCD redraw path is the only place that can also light the
        physical LED/pixel."""
        handler = v3_system.handler
        hw = v3_system.hw
        lcd = handler.lcd
        fs0, fs1 = hw.footswitches[0], hw.footswitches[1]
        fs0.pixel = MagicMock()
        fs1.pixel = MagicMock()
        fs0.add_preset(callback=handler.preset_set_and_change, callback_arg=0)
        fs1.add_preset(callback=handler.preset_set_and_change, callback_arg=1)
        handler.current.preset_index = 1

        lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
        lcd.draw_main_panel()

        fs0.pixel.set_enable.assert_called_once_with(False)
        fs1.pixel.set_enable.assert_called_once_with(True)
        assert fs0.toggled is False
        assert fs1.toggled is True

    def test_active_snapshot_footswitch_is_lit(self, v3_system: SystemFixture):
        handler = v3_system.handler
        hw = v3_system.hw
        lcd = handler.lcd
        fs0, fs1 = hw.footswitches[0], hw.footswitches[1]
        fs0.add_preset(callback=handler.preset_set_and_change, callback_arg=0)
        fs1.add_preset(callback=handler.preset_set_and_change, callback_arg=1)
        handler.current.preset_index = 1

        lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
        lcd.draw_main_panel()

        w0 = next(w for w in lcd.w_footswitches if w.object is fs0)
        w1 = next(w for w in lcd.w_footswitches if w.object is fs1)
        assert w1.is_bypassed is False  # active snapshot -> lit
        assert w0.is_bypassed is True  # inactive snapshot -> dark

    def test_preset_change_relights_indicator(self, v3_system: SystemFixture):
        handler = v3_system.handler
        hw = v3_system.hw
        lcd = handler.lcd
        fs0, fs1 = hw.footswitches[0], hw.footswitches[1]
        fs0.add_preset(callback=handler.preset_set_and_change, callback_arg=0)
        fs1.add_preset(callback=handler.preset_set_and_change, callback_arg=1)

        lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
        lcd.draw_main_panel()

        handler.preset_change(1)

        w0 = next(w for w in lcd.w_footswitches if w.object is fs0)
        w1 = next(w for w in lcd.w_footswitches if w.object is fs1)
        assert w1.is_bypassed is False
        assert w0.is_bypassed is True
