"""LCD footswitch bar for a plugin that publishes a state (loopjefe).

A looper track's switch is MIDI-learned to a `pprops:trigger` port
(`advance`), so the bound parameter's name says nothing useful -- the slot has
to name the *plugin* and show the plugin's own `state` output instead. Both
come from the plugin's LedSpec, which is also what colors the physical LED, so
the LCD and the hardware never disagree.
"""

from common.loop_progress import LoopFill, LoopProgress
from common.parameter import Symbol, Type
from modalapi.plugin import Plugin
from modalapi.ws_protocol import BeatSyncMessage
from plugins import lookup
from pistomp.beatsync import FLASH_US, TickState
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

    name, state, color, loop_icon = handler.lcd._footswitch_state(v3_system.hw.footswitches[0])
    assert (name, state, color, loop_icon) == (None, None, None, False)


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


def _beat(
    handler,
    bar_phase: float,
    beat_phase: float = 0.0,
    is_bar_start: bool = False,
    is_flashing: bool = True,
) -> None:
    """Drive one LED tick with a synthetic transport state."""
    handler._drive_footswitch_leds(
        TickState(
            is_anchored=True,
            is_flashing=is_flashing,
            is_bar_start=is_bar_start,
            bpm=120.0,
            bpb=4.0,
            beat_phase=beat_phase,
            bar_phase=bar_phase,
        )
    )


def test_progress_border_fills_by_bar_and_beat(v3_system: SystemFixture, make_parameter, snapshot):
    """A 4-bar loop playing bar 3, half a bar in, fills 5/8 of the perimeter --
    with a notch at each bar boundary. Loop 2 is stopped: full ring, no fill."""
    handler = v3_system.handler
    lcd = handler.lcd
    plugins = [_loopjefe(make_parameter, "loopjefe_1"), _loopjefe(make_parameter, "loopjefe_2")]
    _bind(v3_system, plugins)

    lcd.link_data(handler.pedalboard_list, handler.current, v3_system.hw.footswitches)
    lcd.draw_main_panel()

    for inst, state in (("loopjefe_1", 4.0), ("loopjefe_2", 5.0)):  # Playback, Stopped
        v3_system.ws_bridge.inject(f"output_set /graph/{inst} state {state}")
        v3_system.ws_bridge.inject(f"output_set /graph/{inst} loop_bars 4.0")
    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 measure_number 2.0")
    handler.poll_ws_messages()

    _beat(handler, 0.5, is_flashing=True)
    lcd.update_footswitches()
    snapshot("play-bar3-beat3")


def test_progress_border_chases_while_recording(v3_system: SystemFixture, make_parameter, snapshot):
    """The first take has no length to be a fraction of, so the border sweeps a
    head instead of filling. Loop 2 is empty: no border at all."""
    handler = v3_system.handler
    lcd = handler.lcd
    plugins = [_loopjefe(make_parameter, "loopjefe_1"), _loopjefe(make_parameter, "loopjefe_2")]
    _bind(v3_system, plugins)

    lcd.link_data(handler.pedalboard_list, handler.current, v3_system.hw.footswitches)
    lcd.draw_main_panel()

    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 state 2.0")  # Recording
    handler.poll_ws_messages()

    _beat(handler, 0.25, is_flashing=True)
    lcd.update_footswitches()
    snapshot("recording-chase")


def test_progress_border_snapshots_at_integer_beat_syncs(v3_system: SystemFixture, make_parameter, snapshot):
    """Capture each integer beat from the transport's synchronized clock."""
    handler = v3_system.handler
    lcd = handler.lcd
    _bind(v3_system, [_loopjefe(make_parameter, "loopjefe_1")])

    lcd.link_data(handler.pedalboard_list, handler.current, v3_system.hw.footswitches)
    lcd.draw_main_panel()
    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 state 4.0")  # Playback
    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 loop_bars 4.0")
    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 measure_number 2.0")
    handler.poll_ws_messages()

    anchor_us = 1_000_000
    beat_period_us = 500_000
    for beat_in_bar in range(4):
        source_us = anchor_us + beat_in_bar * beat_period_us
        v3_system.ws_bridge.inject(f"beat_sync {source_us} 120.0 4 {beat_in_bar}.0")
        handler.poll_ws_messages()
        state = handler.beat_grid.tick(source_us)
        assert state.beat_phase == 0.0
        assert state.bar_phase == beat_in_bar / 4.0
        assert state.is_flashing is True
        handler._drive_footswitch_leds(state)
        lcd.update_footswitches()
        snapshot(f"transport-beat-{beat_in_bar}-on")

    cutoff = anchor_us + 3 * beat_period_us + FLASH_US
    state = handler.beat_grid.tick(cutoff)
    assert state.is_flashing is False
    handler._drive_footswitch_leds(state)
    lcd.update_footswitches()
    snapshot("transport-beat-3-off-50000us")


def test_overdub_past_declared_length_chases(v3_system: SystemFixture, make_parameter):
    """An overdub that outruns the head loop's bar count has no denominator
    left, so it degrades to the chaser rather than filling past 100%."""
    handler = v3_system.handler
    plugins = [_loopjefe(make_parameter, "loopjefe_1")]
    _bind(v3_system, plugins)

    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 state 7.0")  # Overdub
    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 loop_bars 4.0")
    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 measure_number 2.0")
    handler.poll_ws_messages()
    _beat(handler, 0.0)

    fs = v3_system.hw.footswitches[0]
    assert handler.footswitch_loop_progress(fs) == LoopProgress(LoopFill.FILL, (255, 140, 0), 4, 0.5)

    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 measure_number 4.0")
    handler.poll_ws_messages()
    _beat(handler, 0.0)
    assert handler.footswitch_loop_progress(fs) == LoopProgress(LoopFill.CHASE, (255, 140, 0), 0, 0.0)


def test_progress_border_pulses_with_the_beat(v3_system: SystemFixture, make_parameter):
    """The border and physical LED share the binary transport flash state."""
    handler = v3_system.handler
    plugins = [_loopjefe(make_parameter, "loopjefe_1")]
    _bind(v3_system, plugins)
    fs = v3_system.hw.footswitches[0]

    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 state 4.0")  # Playback
    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 loop_bars 4.0")
    handler.poll_ws_messages()

    _beat(handler, 0.0, beat_phase=0.0, is_bar_start=True, is_flashing=True)
    during = handler.footswitch_loop_progress(fs)
    _beat(handler, 0.2, beat_phase=0.8, is_flashing=False)
    outside = handler.footswitch_loop_progress(fs)
    assert during is not None and outside is not None
    assert during.pulse == 1.0
    assert outside.pulse == 0.0

    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 state 5.0")  # Stopped: steady
    handler.poll_ws_messages()
    _beat(handler, 0.2, beat_phase=0.8)
    stopped = handler.footswitch_loop_progress(fs)
    assert stopped is not None and stopped.pulse == 1.0


def test_progress_border_is_steady_without_transport(v3_system: SystemFixture, make_parameter):
    """Without transport, the border remains at its steady brightness."""
    handler = v3_system.handler
    plugins = [_loopjefe(make_parameter, "loopjefe_1")]
    _bind(v3_system, plugins)

    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 state 4.0")
    v3_system.ws_bridge.inject("output_set /graph/loopjefe_1 loop_bars 4.0")
    handler.poll_ws_messages()
    handler.beat_grid.clear()
    handler._drive_footswitch_leds()

    progress = handler.footswitch_loop_progress(v3_system.hw.footswitches[0])
    assert progress is not None and progress.pulse == 1.0
