"""NAV-only (v2, no Tweak encoders) coverage for the NAM capture panel's
setup-view gain/volume knobs — the one panel with no LV2 plugin behind it,
so CLICK opens a synthetic-Parameter audio dialog (open_audio_parameter_dialog)
instead of the generic LV2 one.
"""

from __future__ import annotations

from unittest.mock import patch

from uilib.parameterdialog import Parameterdialog

from pistomp.nam.engine import CaptureState
from pistomp.nam.panel import NamCapturePanel
from tests.types import SystemFixture
from tests.v3.nav_helpers import nav_click
from tests.v3.test_nam_panel import _FakeEngine


def _make_panel(v2_system: SystemFixture, engine: _FakeEngine) -> NamCapturePanel:
    with (
        patch.object(NamCapturePanel, "_create_engine", return_value=engine),
        patch("pistomp.nam.panel.wav_duration", return_value=190.0),
    ):
        panel = NamCapturePanel(output_dir="/tmp", on_dismiss=lambda: None, handler=v2_system.handler)
    v2_system.handler.lcd.pstack.push_panel(panel)
    panel.tick()
    v2_system.handler.poll_lcd_updates()
    return panel


def current_dialog(v2_system: SystemFixture) -> Parameterdialog | None:
    top = v2_system.handler.lcd.pstack.current
    return top if isinstance(top, Parameterdialog) else None


def test_nam_nav_only_initial_render(v2_system: SystemFixture, snapshot):
    _make_panel(v2_system, _FakeEngine(CaptureState.IDLE))
    snapshot("idle")


def test_nam_nav_only_edits_gain(v2_system: SystemFixture, nav_handler, snapshot):
    """Nav to the gain knob (added after Name), CLICK opens its dialog."""
    handler = v2_system.handler
    panel = _make_panel(v2_system, _FakeEngine(CaptureState.IDLE))

    nav_handler(1)  # Name -> gain knob
    handler.poll_lcd_updates()
    snapshot("gain_focused")

    nav_click(handler)
    handler.poll_lcd_updates()
    assert current_dialog(v2_system) is not None
    snapshot("gain_dialog_open")

    nav_handler(8)
    handler.poll_lcd_updates()
    snapshot("gain_dialog_edited")

    nav_click(handler)
    handler.poll_lcd_updates()
    assert current_dialog(v2_system) is None
    snapshot("gain_dialog_closed")

    assert panel._gain_val > -10.0
    assert panel._knob_gain.value == panel._gain_val


def test_nam_nav_only_capturing_no_editor(v2_system: SystemFixture, nav_handler, snapshot):
    """CAPTURING state: knobs aren't even on-screen (capture view), so this
    just confirms the setup-view sel_widgets are gone from the stack."""
    panel = _make_panel(v2_system, _FakeEngine(CaptureState.CAPTURING))

    assert panel._knob_gain not in panel.sel_list
    assert panel._knob_vol not in panel.sel_list
