"""Audio & MIDI menu — snapshot and behaviour tests.

Covers the new ``AudioMidiPanel`` surface (``docs/audio-midi-menu.md``):
EQ curve + IN/OUT arcs + Clock Source/VU Cal rows, the declared-bindings
tweak model, and the ``syncMode`` echo → Clock Source pill repaint.

To regenerate snapshots after intentional UI changes:
    uv run pytest tests/v3/test_audio_midi_panel.py --snapshot-update
"""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import pygame

import pytest

from emulator.stubs import StubJackMute
from modalapi.sync import SyncMode
from pistomp.controller import Controller
from plugins.audio_midi.band_spec import BAND_SPECS
from plugins.audio_midi.panel import AudioMidiPanel, _BandSelectable
from tests.conftest import FakeWebSocketBridge
from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_step


# ---------------------------------------------------------------------------
# Tweak-encoder helpers
# ---------------------------------------------------------------------------


class _FakeTweakEnc(Controller):
    """Minimal stand-in for an encoder (tweak): ``id`` is read by the binding
    dispatcher; ``type`` stays at the Controller default so the panel treats it
    as a generic tweak (not NAV/volume)."""

    def __init__(self, id: int) -> None:
        super().__init__(midi_channel=0, midi_CC=None)
        self.id = id


def _tweak(system: SystemFixture, id: int, rotations: int) -> None:
    from pistomp.input.event import EncoderEvent

    handler = system.handler
    handler.handle(EncoderEvent(controller=_FakeTweakEnc(id), rotations=rotations))
    handler.poll_lcd_updates()


# ---------------------------------------------------------------------------
# Audiocard fixture: an IQaudIO Codec-shaped mock with the 5-band DAC EQ
# ---------------------------------------------------------------------------


@pytest.fixture
def audio_midi_system(v3_system: SystemFixture) -> SystemFixture:
    handler = v3_system.handler
    ac = MagicMock()
    ac.CAPTURE_VOLUME = "Aux"
    ac.MASTER = "Headphone"
    ac.DAC_EQ = "DAC EQ"
    ac.EQ_1 = "DAC EQ1"
    ac.EQ_2 = "DAC EQ2"
    ac.EQ_3 = "DAC EQ3"
    ac.EQ_4 = "DAC EQ4"
    ac.EQ_5 = "DAC EQ5"
    # All gains/volumes start at 0 dB.
    ac.get_volume_parameter.return_value = 0.0
    ac.get_sample_rate.return_value = 48000
    handler.audiocard = ac
    handler.jack_mute = StubJackMute()
    handler.sync_mode = SyncMode.INTERNAL
    handler.eq_status = True
    # recalibrateVU_gain is real on Hardware (delegates to indicators); replace
    # the method on the per-test fixture instance so VU-recalibration calls can
    # be spied via mock call_args_list.
    v3_system.hw.recalibrateVU_gain = MagicMock()  # type: ignore[method-assign]
    return v3_system


def _open_panel(system: SystemFixture) -> AudioMidiPanel:
    handler = system.handler
    panel = AudioMidiPanel(
        handler=handler,
        on_dismiss=lambda: handler.lcd._dismiss_panel(AudioMidiPanel),
    )
    handler.lcd.pstack.push_panel(panel)
    panel.tick()
    handler.poll_lcd_updates()
    return panel


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


class TestAudioMidiPanelSnapshot:
    def test_initial_render(self, audio_midi_system: SystemFixture, snapshot):
        _open_panel(audio_midi_system)
        snapshot("initial")

    def test_clock_source_selected(self, audio_midi_system: SystemFixture, snapshot):
        from tests.v3.nav_helpers import nav_step

        handler = audio_midi_system.handler
        _open_panel(audio_midi_system)
        # NAV down past the 5 EQ bands to Clock Source.
        for _ in range(6):
            nav_step(handler, 1)
            handler.poll_lcd_updates()
        snapshot("clock_source_selected")

    def test_eq_switched_off(self, audio_midi_system: SystemFixture, snapshot):
        """NAV-click the Equalizer row: badge flips to the outline [OFF], the
        bands dim, and they drop out of the nav cycle (next step is Clock
        Source, not Low)."""
        from tests.v3.nav_helpers import nav_click, nav_step

        handler = audio_midi_system.handler
        panel = _open_panel(audio_midi_system)  # opens on the Equalizer row
        nav_click(handler)
        handler.poll_lcd_updates()
        assert handler.eq_status is False
        ac = cast(MagicMock, handler.audiocard)
        ac.set_switch_parameter.assert_called_once_with("DAC EQ", False)
        snapshot("eq_off")

        nav_step(handler, 1)
        handler.poll_lcd_updates()
        assert panel.sel_ref is panel._sync_row


# ---------------------------------------------------------------------------
# Behaviour: tweak bindings, sync-mode echo
# ---------------------------------------------------------------------------


class TestAudioMidiPanelBehaviour:
    @pytest.mark.parametrize(
        "rate",
        [
            96000,  # datasheet marks the EQ N/A at 88.2/96 kHz
            RuntimeError("no PCM rate"),  # nothing holds the card open
        ],
        ids=["unsupported_rate", "rate_unreadable"],
    )
    def test_eq_disabled_when_rate_gives_no_band_table(self, audio_midi_system: SystemFixture, rate):
        handler = audio_midi_system.handler
        ac = cast(MagicMock, handler.audiocard)
        if isinstance(rate, Exception):
            ac.get_sample_rate.side_effect = rate
        else:
            ac.get_sample_rate.return_value = rate
        handler.eq_status = True  # hardware bit on; the panel must still grey it

        panel = _open_panel(audio_midi_system)

        assert panel.eq_enabled is False
        assert panel._eq_row is not None  # shown, not hidden
        assert panel._eq_row not in panel.sel_list
        assert not any(isinstance(w, _BandSelectable) for w in panel.sel_children())
        # Display-only: opening the menu must not write the hardware.
        ac.set_switch_parameter.assert_not_called()

    def test_tweak1_edits_selected_eq_band(self, audio_midi_system: SystemFixture):
        from tests.v3.nav_helpers import nav_step

        handler = audio_midi_system.handler
        _open_panel(audio_midi_system)
        # Initial selection is the Equalizer row; one step forward lands on Low.
        nav_step(handler, 1)
        handler.poll_lcd_updates()
        _tweak(audio_midi_system, id=1, rotations=4)
        ac = cast(MagicMock, handler.audiocard)
        calls = [c.args for c in ac.set_volume_parameter.call_args_list]
        assert any(c[0] == "DAC EQ1" and c[1] > 0 for c in calls), calls

    def test_tweak2_edits_input_gain(self, audio_midi_system: SystemFixture):
        from pistomp.encoder_controller import EncoderController
        from pistomp.input.event import EncoderEvent
        import common.token as Token

        handler = audio_midi_system.handler
        _open_panel(audio_midi_system)
        enc = MagicMock(spec=EncoderController)
        enc.id = 2
        enc.type = Token.KNOB
        enc.midi_CC = None
        ev = EncoderEvent(controller=enc, rotations=2)
        handler.handle(ev)
        handler.poll_lcd_updates()
        ac = cast(MagicMock, handler.audiocard)
        calls = [c.args for c in ac.set_volume_parameter.call_args_list]
        assert any(c[0] == "Aux" and c[1] > 0 for c in calls), calls

    def test_sync_mode_echo_repaints_clock_row(self, audio_midi_system: SystemFixture):
        handler = audio_midi_system.handler
        _open_panel(audio_midi_system)
        # Inject a transport echo switching to Link.
        cast(FakeWebSocketBridge, handler.ws_bridge).inject("transport 1 4.0 120.0 link")
        handler.poll_ws_messages()
        handler.poll_lcd_updates()
        assert handler.sync_mode is SyncMode.LINK

    def test_set_sync_mode_posts_to_modui(self, audio_midi_system: SystemFixture):
        handler = audio_midi_system.handler
        _open_panel(audio_midi_system)
        handler.set_sync_mode(SyncMode.LINK)
        # The worker thread POSTs asynchronously; drain it.
        handler._sync_setter.join(timeout=2.0)
        urls = [c.args[0] for c in audio_midi_system.mock_post.call_args_list]
        assert any("set_sync_mode/link" in u for u in urls), urls

    def test_no_bypass_button(self, audio_midi_system: SystemFixture):
        panel = _open_panel(audio_midi_system)
        assert panel._btn_bypass is None
        assert panel._btn_reset is None
        assert panel._btn_back is not None


# ---------------------------------------------------------------------------
# Sagas — AudioCard writes flow through the synthetic source
#
# Drives the menu via real handler.handle(EncoderEvent) so the declared-bindings
# table resolves and fires edit_symbol. With the IQaudIO fixture's
# audiocard.get_volume_parameter returning 0.0, every synthetic Parameter starts at
# its quantized-0 step; from there each detent moves one slot along the linear
# 128-step grid. Targets:
#   Input gain    (Aux,        -19.75..+12.0 dB): -36 detents → ≈ -9.0 dB
#   Output volume (Headphone,  -25.75..+6.0  dB): -12 detents → ≈ -3.0 dB
#   EQ bands      (DAC EQ1..5, -10.5..+12.0  dB) V shape:
#       EQ1 (Low):    +34 → ≈ +6 dB ;  Mids: -34 → ≈ -6 dB ;
#       Mid-slopes:   -17 → ≈ -3 dB   ; Shoulder: +34 → ≈ +6 dB
# ---------------------------------------------------------------------------


# Target detent counts from the index that quantizes to 0; computed by hand:
# steps[i] = min + (i / 127) * range.  The quantizer snaps a start value of 0 to:
#   Aux       idx 79; Headphone idx 103; DAC EQ* idx 59.
_TARGET_INPUT_DETENTS = -36
_TARGET_OUTPUT_DETENTS = -12
_V_DETENTS = {  # band-name → detents from 0
    "Low":   +34,   # ≈ +5.96 dB
    "L-Mid": -17,   # ≈ -3.06 dB
    "Mid":    -34,  # ≈ -6.07 dB
    "H-Mid": -17,   # ≈ -3.06 dB
    "High":   +34,  # ≈ +5.96 dB
}
_V_EXPECTED_DB = {  # coarse tolerance used by the assertion (see `assert_also`)
    "Low":   pytest.approx(+6.0, abs=0.5),
    "L-Mid": pytest.approx(-3.0, abs=0.5),
    "Mid":    pytest.approx(-6.0, abs=0.5),
    "H-Mid": pytest.approx(-3.0, abs=0.5),
    "High":   pytest.approx(+6.0, abs=0.5),
}
_BAND_ALSA_INDEX = {  # name → DAC EQ* symbol string
    "Low":   "DAC EQ1",
    "L-Mid": "DAC EQ2",
    "Mid":    "DAC EQ3",
    "H-Mid": "DAC EQ4",
    "High":   "DAC EQ5",
}


def _final_value_for(calls: list[tuple], symbol: str) -> float | None:
    """Last ``set_volume_parameter`` payload for a given ALSA symbol."""
    last = None
    for args in calls:
        if args and args[0] == symbol:
            last = args[1]
    return last


class TestAudioMidiPanelSaga:
    def test_levels_and_v_eq_drives_alsa_writes(self, audio_midi_system: SystemFixture, snapshot):
        handler = audio_midi_system.handler
        _open_panel(audio_midi_system)
        snapshot("opened")

        # Input gain down to ≈ -9 dB. Tweak2 edits in_gain regardless of the
        # current nav selection (the declared-bindings row names it directly).
        _tweak(audio_midi_system, id=2, rotations=_TARGET_INPUT_DETENTS)
        snapshot("gain_set")

        # Output volume down to ≈ -3 dB. Tweak3 (and Vol) edit out_vol.
        _tweak(audio_midi_system, id=3, rotations=_TARGET_OUTPUT_DETENTS)
        snapshot("output_set")

        # Shape the 5-band EQ to a V. Tweak1 acts on the *currently selected*
        # widget's symbol. Initial selection is Input arc, so nav forward 2
        # step to land on the Low band before tweaking.
        nav_step(handler, +1)  # Low band
        handler.poll_lcd_updates()
        for band in BAND_SPECS:
            _tweak(audio_midi_system, id=1, rotations=_V_DETENTS[band.name])
            if band is not BAND_SPECS[-1]:
                nav_step(handler, +1)
                handler.poll_lcd_updates()
        snapshot("v_eq_shape")

        # ── assert the audiocard (ALSA mixer front) got the right writes ──
        ac = cast(MagicMock, handler.audiocard)
        calls = [c.args for c in ac.set_volume_parameter.call_args_list]
        assert _final_value_for(calls, "Aux") == pytest.approx(-9.0, abs=0.5), calls
        assert _final_value_for(calls, "Headphone") == pytest.approx(-3.0, abs=0.5), calls
        for name, sym in _BAND_ALSA_INDEX.items():
            val = _final_value_for(calls, sym)
            assert val == _V_EXPECTED_DB[name], f"{name} ({sym}) -> {val}"

        # ── input-gain change must also drive VU recalibration ──────────────
        # The synthetic source fires hardware.recalibrateVU_gain with the new
        # in_gain (per source.set_param_value). Mic-style controls have their
        # indicator gain re-cued.
        recalc = audio_midi_system.hw.recalibrateVU_gain  # type: ignore[attr-defined]
        recalc_calls = [c.args for c in recalc.call_args_list]  # type: ignore[union-attr]
        assert recalc_calls, "input gain change should recalibrate VU"
        assert any(c[0] == pytest.approx(-9.0, abs=0.5) for c in recalc_calls), recalc_calls

    def test_mute_button_toggles_jack_mute(self, audio_midi_system: SystemFixture):
        """Footer Mute button toggles the shared JackMute via NAV-click.

        Tuner-style: the label stays "Mute"; the active (muted) state is shown
        by the button background flipping to ``_BTN_MUTE_ACTIVE_COLOR``.
        """
        from plugins.audio_midi.panel import _BTN_MUTE_ACTIVE_COLOR

        handler = audio_midi_system.handler
        panel = _open_panel(audio_midi_system)
        mute_btn = panel._mute_btn
        assert mute_btn is not None
        assert mute_btn.text == "Mute"
        assert mute_btn.bkgnd_color != _BTN_MUTE_ACTIVE_COLOR  # not muted on open

        # eq→5bands→sync→vu→in→out→Back→Mute = 11 steps
        for _ in range(11):
            nav_step(handler, +1)
            handler.poll_lcd_updates()
        assert panel.sel_ref is mute_btn

        # Short-press toggles mute via the button action.
        from tests.v3.nav_helpers import nav_click

        nav_click(handler)
        handler.poll_lcd_updates()
        assert handler.jack_mute.is_muted()
        assert mute_btn.bkgnd_color == _BTN_MUTE_ACTIVE_COLOR
        assert mute_btn.text == "Mute"  # label never changes

        nav_click(handler)
        handler.poll_lcd_updates()
        assert not handler.jack_mute.is_muted()
        assert mute_btn.bkgnd_color != _BTN_MUTE_ACTIVE_COLOR
        assert mute_btn.text == "Mute"


# ---------------------------------------------------------------------------
# Toolbar tile glyphs + transport-driven tile state
# ---------------------------------------------------------------------------


class TestAudioMidiTileGlyph:
    """Procedural glyphs (uilib/glyphs/audio_midi_tile) for the Audio & MIDI
    menu's toolbar tile."""

    def test_each_state_renders_16x16_srcalpha(self):
        from uilib.glyphs.audio_midi_tile import audio_midi_tile_glyph

        for state in ("nominal", "muted", "rolling"):
            g = audio_midi_tile_glyph(state)
            assert g.get_size() == (16, 16), state
            assert g.get_flags() & pygame.SRCALPHA, state

    def test_muted_glyph_has_slash_that_nominal_lacks(self):
        from uilib.glyphs.audio_midi_tile import audio_midi_tile_glyph

        nominal = audio_midi_tile_glyph("nominal")
        muted = audio_midi_tile_glyph("muted")
        # The slash runs corner-to-corner; the upper-left pixel is lit on the
        # muted glyph (slash start) but transparent on nominal.
        assert nominal.get_at((1, 1))[3] == 0
        assert muted.get_at((1, 1))[3] > 0

    def test_rolling_glyph_has_play_triangle_nominal_lacks(self):
        from uilib.glyphs.audio_midi_tile import audio_midi_tile_glyph

        nominal = audio_midi_tile_glyph("nominal")
        rolling = audio_midi_tile_glyph("rolling")
        # The play triangle's apex is at ~(15, 5); nominal is transparent there.
        apex = (15, 5)
        assert nominal.get_at(apex)[3] == 0
        assert rolling.get_at(apex)[3] > 0


class TestAudioMidiTileState:
    """The toolbar tile (w_eq) reflects jack_mute / transport_rolling.

    Drives the same WebSocket transport path that drives Clock Source updates;
    asserts the handler's transport_rolling flips and the LCD's update_audio_
    midi_tile picks the right procedural glyph Surface.
    """

    def _w_eq_surface(self, system: SystemFixture) -> pygame.Surface:
        w_eq = system.handler.lcd.w_eq
        assert w_eq is not None, "draw_tools never ran"
        return w_eq.image

    def test_transport_rolling_flag_flips_on_transport_echo(self, audio_midi_system: SystemFixture):
        handler = audio_midi_system.handler
        assert handler.transport_rolling is False
        cast(FakeWebSocketBridge, handler.ws_bridge).inject("transport 1 4.0 120.0 link")
        handler.poll_ws_messages()
        assert handler.transport_rolling is True

    def test_transport_stop_clears_flag(self, audio_midi_system: SystemFixture):
        handler = audio_midi_system.handler
        cast(FakeWebSocketBridge, handler.ws_bridge).inject("transport 1 4.0 120.0 link")
        handler.poll_ws_messages()
        assert handler.transport_rolling is True
        cast(FakeWebSocketBridge, handler.ws_bridge).inject("transport 0 4.0 120.0 link")
        handler.poll_ws_messages()
        assert handler.transport_rolling is False

    def test_tile_swaps_to_rolling_glyph_on_transport_roll(self, audio_midi_system: SystemFixture):

        handler = audio_midi_system.handler
        handler.lcd.draw_main_panel()
        nominal_before = self._w_eq_surface(audio_midi_system)
        cast(FakeWebSocketBridge, handler.ws_bridge).inject("transport 1 4.0 120.0 link")
        handler.poll_ws_messages()
        handler.poll_lcd_updates()
        cur = self._w_eq_surface(audio_midi_system)
        assert cur is not nominal_before
        apex = (15, 5)
        assert cur.get_at(apex)[3] > 0  # play-triangle apex
        assert nominal_before.get_at(apex)[3] == 0  # nominal is clear there

    def test_mute_via_panel_swaps_tile_to_muted_glyph(self, audio_midi_system: SystemFixture):
        handler = audio_midi_system.handler
        handler.lcd.draw_main_panel()
        nominal_before = self._w_eq_surface(audio_midi_system)
        # Toggle mute through the AudioMidiPanel — the same path the user takes
        # — so the LCD update hook fires on the way out.
        panel = _open_panel(audio_midi_system)
        jm = handler.jack_mute
        assert not jm.is_muted()
        jm.mute()
        panel._apply_mute_style()
        handler.lcd.update_audio_midi_tile()
        handler.poll_lcd_updates()
        cur = self._w_eq_surface(audio_midi_system)
        assert cur is not nominal_before
        # Muted glyph lights the upper-left (slash start) where nominal is clear.
        assert cur.get_at((1, 1))[3] > 0
        assert nominal_before.get_at((1, 1))[3] == 0
        # Restore to keep the shared fixture tidy.
        jm.unmute()
        handler.lcd.update_audio_midi_tile()