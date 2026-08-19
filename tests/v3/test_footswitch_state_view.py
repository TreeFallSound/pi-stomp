"""LCD footswitch bar for a plugin that publishes a state (loopjefe).

A looper track's switch is MIDI-learned to a `pprops:trigger` port
(`advance`), so the bound parameter's name says nothing useful -- the slot has
to name the *plugin* and show the plugin's own `state` output instead. Both
come from the plugin's LedSpec, which is also what colors the physical LED, so
the LCD and the hardware never disagree.
"""

from common.parameter import Symbol, Type
from modalapi.plugin import Plugin
from plugins import lookup
from plugins.loopjefe import LOOPJEFE_URIS
from tests.types import SystemFixture


def _loopjefe(make_parameter, instance_id: str) -> Plugin:
    advance = make_parameter("advance", instance_id, value=0.0)
    advance.type = Type.TRIGGER  # pprops:trigger in loopjefe.ttl
    uri = LOOPJEFE_URIS[0]
    return Plugin(
        instance_id,
        {Symbol("advance"): advance},
        {},
        "Looper",
        uri=uri,
        customization=lookup(uri),
    )


def _bind(v3_system: SystemFixture, plugins: list[Plugin]) -> None:
    """Learn each plugin's `advance` onto the footswitch of the same index."""
    handler = v3_system.handler
    assert handler.current
    handler.current.pedalboard.plugins = plugins
    for i, plugin in enumerate(plugins):
        fs = v3_system.hw.footswitches[i]
        binding = next(k for k, c in v3_system.hw.controllers.items() if c is fs)
        channel, cc = binding.split(":")
        v3_system.ws_bridge.inject(f"midi_map /graph/{plugin.instance_id} advance {channel} {cc} 0.0 1.0")
    handler.poll_ws_messages()


def test_two_track_looper_footswitch_bar(v3_system: SystemFixture, make_parameter, snapshot):
    """Two looper tracks, each mid-flight in a different state."""
    handler = v3_system.handler
    lcd = handler.lcd
    plugins = [_loopjefe(make_parameter, "loopjefe_1"), _loopjefe(make_parameter, "loopjefe_2")]
    _bind(v3_system, plugins)

    lcd.link_data(handler.pedalboard_list, handler.current, v3_system.hw.footswitches)
    lcd.draw_main_panel()
    snapshot("empty")

    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 state 2.0")  # Recording
    v3_system.ws_bridge.inject("output_set /graph/loopjefe_2 state 4.0")  # Playback
    handler.poll_ws_messages()
    lcd.update_footswitches()
    snapshot("recording-and-playback")


def test_state_view_falls_back_when_plugin_has_no_led_spec(v3_system: SystemFixture, make_parameter):
    """A plugin without a LedSpec keeps the ordinary dot-and-label slot -- the
    state view must not leak onto every bound footswitch."""
    handler = v3_system.handler
    assert handler.current

    param = make_parameter("gain", "/Reverb", value=0.0)
    plugin = Plugin("/Reverb", {Symbol("gain"): param}, {}, "Reverb")
    handler.current.pedalboard.plugins = [plugin]

    name, state, color = handler.lcd._footswitch_state(v3_system.hw.footswitches[0])
    assert (name, state, color) == (None, None, None)


def test_state_view_repaints_on_output_set(v3_system: SystemFixture, make_parameter, snapshot):
    """The plugin's state arrives asynchronously over the socket, long after the
    press that caused it. Without a repaint on `output_set` the slot keeps
    whatever it painted at press time and the looper reads "Empty" forever."""
    handler = v3_system.handler
    lcd = handler.lcd
    plugins = [_loopjefe(make_parameter, "loopjefe_1"), _loopjefe(make_parameter, "loopjefe_2")]
    _bind(v3_system, plugins)

    lcd.link_data(handler.pedalboard_list, handler.current, v3_system.hw.footswitches)
    lcd.draw_main_panel()

    # No press, no reload -- only the socket tells us the looper moved.
    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 state 7.0")  # Overdub
    handler.poll_ws_messages()
    snapshot("overdub-from-output-set")
