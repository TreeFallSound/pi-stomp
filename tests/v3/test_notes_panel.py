"""Snapshot saga for the Notes LV2 plugin full-screen panel.

Exercises: open → read → scroll to bottom → close via Back (nav encoder press).

To regenerate snapshots after intentional UI changes:
    uv run pytest tests/v3/test_notes_panel.py --snapshot-update
"""

import pistomp.switchstate as switchstate
from modalapi.parameter import Parameter
from modalapi.plugin import Plugin
from pistomp.controller import Controller
from pistomp.input.event import EncoderEvent
from plugins.customization import lookup
from plugins.notes import NOTES_URI
from plugins.notes.panel import NotesData, NotesPanel
from tests.types import SystemFixture
import common.token as Token

# ── sample text long enough to require scrolling ──────────────────────────────

_NOTES_TEXT = """\
HOW TO USE THIS PEDALBOARD

Signal flows left to right. Each tile is one plugin.

FOOTSWITCHES
Long-press any footswitch to toggle it into latching mode.
Short-press cycles the assigned parameter.

ENCODERS
Tweak 1: Input gain
Tweak 2: Master volume
Tweak 3: Reverb mix

BLEND PEDAL
The expression pedal blends between the Clean and Fuzz snapshots. Move it slowly to avoid clicks.

TIPS
- Use Shift+Enter in MOD UI to add new lines here.
- Font size is adjustable in the plugin settings.
- Around 450 characters maximum.
"""


# ── helpers ───────────────────────────────────────────────────────────────────


class _NavEnc(Controller):
    """Fake nav encoder — type=NAV so the notes panel intercepts rotations."""

    def __init__(self) -> None:
        super().__init__(midi_channel=0, midi_CC=None)
        self.type = Token.NAV
        self.id = 0


def make_notes_plugin(instance_id: str = "notes_1") -> Plugin:
    bypass_info = {"shortName": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}
    params: dict[str, Parameter] = {
        ":bypass": Parameter(bypass_info, 0.0, None, instance_id),
    }
    plugin = Plugin(
        instance_id,
        params,
        {},
        "Utility",
        uri=NOTES_URI,
        customization=lookup(NOTES_URI),
        extra_data=NotesData(text=_NOTES_TEXT),
    )
    plugin.has_footswitch = False
    plugin.pedalboard_snapshot = {":bypass": 0.0}
    return plugin


def open_notes(v3_system: SystemFixture) -> Plugin:
    handler = v3_system.handler
    hw = v3_system.hw

    assert handler.current
    plugin = make_notes_plugin()
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    handler.show_fullscreen_panel(plugin, NotesPanel)
    handler.poll_lcd_updates()
    return plugin


def scroll(handler, rotations: int) -> None:
    """Rotate the nav encoder by `rotations` detents and poll."""
    event = EncoderEvent(
        controller=_NavEnc(),
        rotations=rotations,
        new_value=0.0,
        new_midi_value=0,
    )
    handler.handle(event)
    handler.poll_lcd_updates()


# ── saga ──────────────────────────────────────────────────────────────────────


def test_notes_panel_saga(v3_system: SystemFixture, snapshot):
    """Open notes panel, read, scroll to bottom, close."""
    handler = v3_system.handler

    open_notes(v3_system)
    snapshot("opened")

    # Scroll down a few lines — should show the middle of the text.
    scroll(handler, 4)
    snapshot("scrolled_mid")

    # Scroll far past the end — should clamp at the last window.
    scroll(handler, 50)
    snapshot("at_bottom")

    # Press the nav encoder (RELEASED = short press) → activates Back button.
    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    handler.poll_lcd_updates()
    snapshot("closed")
