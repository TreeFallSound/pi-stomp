"""Bidirectional sync between a footswitch and a *non-:bypass* plugin parameter
(e.g. mixer/Solo1) it's bound to.

Two coupled invariants:
  A. A footswitch PRESS writes the parameter to the polarity `set_value` reads
     back — "on" is the max end for a non-:bypass toggle, not 0 (the :bypass
     polarity). See Footswitch.set_value.
  B. A parameter change committed from the UI (the parameter dialog / On-Off
     menu, a tweak encoder) drives the footswitch's toggled/LED/pixel through
     the same mirror the mod-host echo runs — it must not wait for a round-trip.
"""

from typing import cast

from common.parameter import BYPASS_SYMBOL
from pistomp.input.event import SwitchEvent, SwitchEventKind
from plugins.window import PluginWindow
from tests.types import SystemFixture


class _BarePanel(PluginWindow[None]):
    def snapshot_state(self) -> None:
        return None

    def apply_state(self, state: None) -> None:
        pass

    def build_widgets(self) -> None:
        pass


def _bind_solo_footswitch(v3_system: SystemFixture, make_plugin, make_parameter):
    """Bind footswitch 0 to a non-:bypass TOGGLED param, starting OFF (min)."""
    handler = v3_system.handler
    hw = v3_system.hw
    ch = hw.midi_channel
    fs0 = hw.footswitches[0]
    binding = f"{ch}:{fs0.midi_CC}"

    plugin = make_plugin("mixer", has_footswitch=True)
    solo = make_parameter("Solo1", "mixer", value=0.0, minimum=0.0, maximum=1.0)
    solo.binding = binding
    plugin.parameters[solo.symbol] = solo

    handler.current.pedalboard.plugins = [plugin]
    handler.bind_current_pedalboard()
    return handler, fs0, solo


# ── Direction A: footswitch press writes the parameter with correct polarity ──


def test_press_on_writes_param_to_max(v3_system: SystemFixture, make_plugin, make_parameter):
    handler, fs0, solo = _bind_solo_footswitch(v3_system, make_plugin, make_parameter)
    assert fs0.toggled is False
    assert solo.symbol != BYPASS_SYMBOL

    event = SwitchEvent(controller=fs0, kind=SwitchEventKind.PRESS, timestamp=1000.0)
    assert handler.handle(event) is True

    assert fs0.toggled is True
    # "on" for a non-:bypass param is the max end, not the :bypass 0.
    assert solo.value == solo.maximum


def test_press_off_writes_param_to_min(v3_system: SystemFixture, make_plugin, make_parameter):
    handler, fs0, solo = _bind_solo_footswitch(v3_system, make_plugin, make_parameter)
    fs0.toggled = True
    solo.value = solo.maximum

    event = SwitchEvent(controller=fs0, kind=SwitchEventKind.PRESS, timestamp=1000.0)
    assert handler.handle(event) is True

    assert fs0.toggled is False
    assert solo.value == solo.minimum


# ── Direction B: a foreign parameter write drives the footswitch ──────────────


def test_menu_commit_on_toggles_footswitch(v3_system: SystemFixture, make_plugin, make_parameter):
    handler, fs0, solo = _bind_solo_footswitch(v3_system, make_plugin, make_parameter)
    assert fs0.toggled is False

    handler.parameter_value_commit(solo, solo.maximum)  # the On/Off menu / tweak path

    assert fs0.toggled is True


def test_menu_commit_off_toggles_footswitch(v3_system: SystemFixture, make_plugin, make_parameter):
    handler, fs0, solo = _bind_solo_footswitch(v3_system, make_plugin, make_parameter)
    handler.parameter_value_commit(solo, solo.maximum)
    assert fs0.toggled is True

    handler.parameter_value_commit(solo, solo.minimum)

    assert fs0.toggled is False


def test_menu_commit_refreshes_footswitch(v3_system: SystemFixture, make_plugin, make_parameter):
    """The commit reaches the paint path, not just internal state."""
    handler, fs0, solo = _bind_solo_footswitch(v3_system, make_plugin, make_parameter)

    seen: list[bool] = []
    fs0.refresh_callback = lambda **kw: seen.append(fs0.toggled)

    handler.parameter_value_commit(solo, solo.maximum)

    assert seen and seen[-1] is True


# ── The tweak path: PluginPanel.set_param (ParameterWindow) must mirror too ────


def test_tweak_setparam_on_toggles_footswitch(v3_system: SystemFixture, make_plugin, make_parameter):
    """A tweak edit commits through PluginPanel.set_param, not
    parameter_value_commit — it must reconcile the footswitch identically."""
    handler, fs0, solo = _bind_solo_footswitch(v3_system, make_plugin, make_parameter)
    plugin = handler.current.pedalboard.plugins[0]
    handler.show_fullscreen_panel(plugin, _BarePanel)
    panel = cast(_BarePanel, handler.lcd.pstack.current)
    assert fs0.toggled is False

    panel.set_param(solo.symbol, solo.maximum)

    assert fs0.toggled is True


def test_tweak_setparam_off_toggles_footswitch(v3_system: SystemFixture, make_plugin, make_parameter):
    handler, fs0, solo = _bind_solo_footswitch(v3_system, make_plugin, make_parameter)
    plugin = handler.current.pedalboard.plugins[0]
    handler.show_fullscreen_panel(plugin, _BarePanel)
    panel = cast(_BarePanel, handler.lcd.pstack.current)
    panel.set_param(solo.symbol, solo.maximum)
    assert fs0.toggled is True

    panel.set_param(solo.symbol, solo.minimum)

    assert fs0.toggled is False
