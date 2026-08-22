"""Per-pedalboard hardware config overlay — reinit correctness tests."""

import pistomp.config as config
from pistomp.config.adapt_v1 import adapt
from pistomp.config.schema_v1 import merge
from tests.types import SystemFixture
from common.parameter import Parameter, PortInfo, Symbol

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(hw, footswitches=None, encoders=None, analog_controls=None) -> config.PedalboardConfig:
    """Resolve a pedalboard overlay against the fixture's default_config.yml."""
    section: dict = {}
    if footswitches is not None:
        section["footswitches"] = footswitches
    if encoders is not None:
        section["encoders"] = encoders
    if analog_controls is not None:
        section["analog_controllers"] = analog_controls
    overlay = config.parse({"hardware": section}, "<test>")
    return adapt(merge(hw.default_cfg, overlay))


# ---------------------------------------------------------------------------
# Footswitch longpress — existing behaviour
# ---------------------------------------------------------------------------


def test_footswitch_longpress_set_from_default(v3_system: SystemFixture):
    """FS0 longpress comes from default_config after fixture setup."""
    hw = v3_system.hw
    assert "previous_snapshot" in hw.footswitches[0].longpress_groups


def test_footswitch_longpress_override(v3_system: SystemFixture):
    """Pedalboard config can change FS0 longpress to a different action."""
    hw = v3_system.hw

    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "longpress": "toggle_bypass"}]))

    assert "toggle_bypass" in hw.footswitches[0].longpress_groups


def test_footswitch_longpress_reset_to_default(v3_system: SystemFixture):
    """After an override, reinit(None) restores the default longpress."""
    hw = v3_system.hw

    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "longpress": "toggle_bypass"}]))
    hw.reinit(adapt(merge(hw.default_cfg)))

    assert "previous_snapshot" in hw.footswitches[0].longpress_groups
    assert "toggle_bypass" not in hw.footswitches[0].longpress_groups


def test_footswitch_unmentioned_keeps_default_longpress(v3_system: SystemFixture):
    hw = v3_system.hw
    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "preset": 2}]))
    assert "previous_snapshot" in hw.footswitches[0].longpress_groups


def test_footswitch_longpress_suppress_with_none(v3_system: SystemFixture):
    """Explicit null longpress in pedalboard config clears the default."""
    hw = v3_system.hw

    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "longpress": None}]))

    assert len(hw.footswitches[0].longpress_groups) == 0


# ---------------------------------------------------------------------------
# Footswitch color — existing behaviour
# ---------------------------------------------------------------------------


def test_footswitch_color_override(v3_system: SystemFixture):
    """Pedalboard config can set FS0 lcd_color."""
    hw = v3_system.hw

    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "color": "Red"}]))

    assert hw.footswitches[0].lcd_color == "Red"


def test_footswitch_color_cleared_without_key(v3_system: SystemFixture):
    """A pedalboard that sets no color gets the default, not the color of the
    pedalboard before it."""
    hw = v3_system.hw

    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "color": "Red"}]))
    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "longpress": "toggle_bypass"}]))

    assert hw.footswitches[0].lcd_color is None


def test_footswitch_preset_cleared_without_key(v3_system: SystemFixture):
    """The same rule for preset. Nothing carries over from the last pedalboard."""
    hw = v3_system.hw

    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "preset": "UP"}]))
    assert hw.footswitches[0].preset_direction == "UP"

    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "color": "Red"}]))
    assert hw.footswitches[0].preset_direction is None


def test_footswitch_state_cleared_on_reinit(v3_system: SystemFixture):
    """Toggle, label, category and plugin binding do not survive a pedalboard
    change. get_display_label falls back to "" only when both midi_CC and
    preset_callback_arg are clear, so a stale binding bleeds a dead label."""
    hw = v3_system.hw
    fs = hw.footswitches[0]

    fs.toggled = True
    fs.set_display_label("Reverb")
    fs.set_category("Delay")
    activation = v3_system.handler.current.activation
    assert activation is not None
    activation.attach(fs, hw.create_external_parameter("probe", 0, 1))
    v3_system.handler.current.close()

    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "preset": 1}]))

    assert fs.toggled is False
    assert fs.category is None
    assert fs.parameter is None
    assert fs.display_label == "1"


def test_footswitch_binding_applies_by_id_not_position(v3_system: SystemFixture):
    """Config is keyed by id. A footswitch missing from the object list must
    not shift a later id's config onto the wrong switch."""
    hw = v3_system.hw
    kept = [fs for fs in hw.footswitches if fs.id != 1]
    hw.footswitches = kept

    hw.reinit(_cfg(hw, footswitches=[{"id": 2, "color": "Red"}]))

    by_id = {fs.id: fs for fs in kept}
    assert by_id[2].lcd_color == "Red"
    assert by_id[0].lcd_color is None
    assert by_id[3].lcd_color is None


def test_disabled_footswitch_still_takes_its_other_fields(v3_system: SystemFixture):
    """disable does not stop the rest of the entry from applying, so a disabled
    switch cannot keep the colour of the pedalboard before it."""
    hw = v3_system.hw

    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "color": "Red"}]))
    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "disable": True, "color": "Blue"}]))

    assert hw.footswitches[0].disabled is True
    assert hw.footswitches[0].lcd_color == "Blue"


# ---------------------------------------------------------------------------
# Footswitch disable — NEW: expected to fail until fix lands
# ---------------------------------------------------------------------------


def test_footswitch_disable_override(v3_system: SystemFixture):
    """Pedalboard config can mark FS0 as disabled."""
    hw = v3_system.hw

    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "disable": True}]))

    assert hw.footswitches[0].disabled is True


def test_footswitch_disable_reset_to_enabled(v3_system: SystemFixture):
    """Disabled FS resets to enabled when a different pedalboard is loaded."""
    hw = v3_system.hw

    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "disable": True}]))
    hw.reinit(adapt(merge(hw.default_cfg)))  # new pedalboard with no overrides

    assert hw.footswitches[0].disabled is False


def test_footswitch_disabled_does_not_respond(v3_system: SystemFixture):
    """A disabled footswitch ignores poll() events."""

    hw = v3_system.hw
    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "disable": True}]))

    fs0 = hw.footswitches[0]
    fires = []
    original_on_switch = fs0._on_switch
    fs0._on_switch = lambda state, timestamp=0.0: fires.append(state)

    # Simulate a poll (bypass the GPIO layer)
    fs0.poll()  # should no-op because disabled

    # Nothing fired
    assert fires == []

    # Restore
    fs0._on_switch = original_on_switch


# ---------------------------------------------------------------------------
# Encoder longpress — stored as string name; resolved by handler at dispatch.
# ---------------------------------------------------------------------------


def _enc(hw, enc_id):
    return next(e for e in hw.encoders if getattr(e, "id", None) == enc_id)


def test_encoder_longpress_set_from_default(v3_system: SystemFixture):
    """Enc1 longpress name matches default_config (previous_snapshot) after boot."""
    hw = v3_system.hw

    assert _enc(hw, 1).longpress == "previous_snapshot"


def test_encoder_longpress_override(v3_system: SystemFixture):
    """Pedalboard config can change enc1 longpress to toggle_bypass."""
    hw = v3_system.hw

    hw.reinit(_cfg(hw, encoders=[{"id": 1, "longpress": "toggle_bypass"}]))

    assert _enc(hw, 1).longpress == "toggle_bypass"


def test_encoder_longpress_reset_to_default(v3_system: SystemFixture):
    """After an encoder longpress override, reinit(None) restores the default."""
    hw = v3_system.hw

    hw.reinit(_cfg(hw, encoders=[{"id": 1, "longpress": "toggle_bypass"}]))
    hw.reinit(adapt(merge(hw.default_cfg)))

    assert _enc(hw, 1).longpress == "previous_snapshot"


def test_encoder_longpress_suppress_with_none(v3_system: SystemFixture):
    """Explicit null in pedalboard config clears the default encoder longpress."""
    hw = v3_system.hw

    hw.reinit(_cfg(hw, encoders=[{"id": 1, "longpress": None}]))

    assert _enc(hw, 1).longpress is None


def test_encoder_unmentioned_keeps_default(v3_system: SystemFixture):
    """Overriding enc2 does not disturb enc1's default longpress."""
    hw = v3_system.hw

    hw.reinit(_cfg(hw, encoders=[{"id": 2, "longpress": "toggle_bypass"}]))

    assert _enc(hw, 1).longpress == "previous_snapshot"


def test_encoder_longpress_cleared_when_default_omits_it(v3_system: SystemFixture):
    """Encoder 3 is the VOLUME encoder and carries no longpress in
    default_config.yml. An override must still go away with the pedalboard."""
    hw = v3_system.hw
    enc = _enc(hw, 3)

    hw.reinit(_cfg(hw, encoders=[{"id": 3, "longpress": "toggle_bypass"}]))
    assert enc.longpress == "toggle_bypass"

    hw.reinit(adapt(merge(hw.default_cfg)))
    assert enc.longpress is None


def test_external_midi_messages_do_not_accumulate(v3_system: SystemFixture):
    """Messages belong to the pedalboard that declared them."""
    hw = v3_system.hw
    assert hw.external_midi is not None

    first = {"hardware": {"external_midi": {"enabled": True, "messages": {"HX Stomp": [[0xC0, 0x01]]}}}}
    hw.reinit(adapt(merge(hw.default_cfg, config.parse(first, "<test>"))))
    assert "HX Stomp" in hw.external_midi.messages

    hw.reinit(adapt(merge(hw.default_cfg)))
    assert hw.external_midi.messages == {}


def test_longpress_names_cover_every_handler_callback(v3_system: SystemFixture):
    """The accepted longpress names and the handler's callback map must not
    drift. A name the handler answers to but the parser rejects fails the whole
    config on load."""
    from typing import get_args

    from pistomp.config.schema_v1 import LongpressName

    # set_mod_tap_tempo shares the callback map but is reachable only via the
    # `tap_tempo:` key, which passes a BPM no longpress can supply.
    assert set(v3_system.handler.callbacks) - {"set_mod_tap_tempo"} == set(get_args(LongpressName))


def test_reinit_unsubscribes_old_parameter(v3_system: SystemFixture):
    hw = v3_system.hw
    fs = hw.footswitches[0]
    old_param = Parameter(
        PortInfo(name="Bypass", symbol=Symbol("bypass"), ranges={"minimum": 0.0, "maximum": 1.0}),
        0.0,
        "0:60",
        "OldPlugin",
    )
    activation = v3_system.handler.current.activation
    assert activation is not None
    activation.bind(fs, old_param)

    v3_system.handler.current.close()
    hw.reinit(_cfg(hw, footswitches=[{"id": 0, "preset": 1}]))
    fs.toggled = True
    old_param.reconcile(1.0)

    assert fs.parameter is None
    assert fs.toggled is True


def test_encoder_disable_removes_controller(v3_system: SystemFixture):
    hw = v3_system.hw
    enc = _enc(hw, 1)

    hw.reinit(_cfg(hw, encoders=[{"id": 1, "disable": True}]))

    assert all(controller is not enc for controller in hw.controllers.values())




def test_encoder_type_transition_rebinds_volume(v3_system: SystemFixture):
    hw = v3_system.hw
    enc = _enc(hw, 1)

    hw.reinit(_cfg(hw, encoders=[{"id": 1, "type": "VOLUME"}]))
    v3_system.handler.bind_volume_encoder()

    assert enc.type == "VOLUME"
    assert enc.parameter is v3_system.handler.volume_parameter
