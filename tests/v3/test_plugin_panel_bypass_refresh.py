"""Bypassing a plugin from inside its custom parameter panel must update the
main pedalboard grid tile once the panel is dismissed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from modalapi.plugin import Plugin
from plugins.fullscreen import FullscreenPluginPanel
from plugins.window import PluginWindow
from tests.types import SystemFixture


@dataclass
class _NoState:
    pass


class _DemoFullscreenPanel(FullscreenPluginPanel[_NoState]):
    def snapshot_state(self) -> _NoState:
        return _NoState()

    def apply_state(self, state: _NoState) -> None:
        pass

    def build_widgets(self) -> None:
        pass


class _DemoWindowPanel(PluginWindow[_NoState]):
    def snapshot_state(self) -> _NoState:
        return _NoState()

    def apply_state(self, state: _NoState) -> None:
        pass

    def build_widgets(self) -> None:
        pass


def _install_plugin(v3_system: SystemFixture, make_plugin) -> Plugin:
    handler = v3_system.handler
    hw = v3_system.hw
    assert handler.current
    plugin = make_plugin("demo", category="Utility", bypassed=False)
    handler.current.pedalboard.plugins = [plugin]
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()
    return plugin


def _tile_for(v3_system: SystemFixture, plugin: Plugin):
    for w in v3_system.handler.lcd.w_plugins:
        if w.object is plugin:
            return w
    raise AssertionError("no grid tile found for plugin")


def _assert_tile_matches_bypass_state(tile, plugin: Plugin) -> None:
    """Mirrors Lcd320x240.color_plugin's outline/background contract."""
    if plugin.is_bypassed():
        assert tile.outline == 1
    else:
        assert tile.outline == 0


def test_fullscreen_panel_bypass_refreshes_grid_tile(v3_system: SystemFixture, make_plugin):
    handler = v3_system.handler
    plugin = _install_plugin(v3_system, make_plugin)
    tile = _tile_for(v3_system, plugin)
    _assert_tile_matches_bypass_state(tile, plugin)

    handler.show_fullscreen_panel(plugin, _DemoFullscreenPanel)
    panel = cast(_DemoFullscreenPanel, handler._fullscreen_panel)
    assert panel is not None
    panel._on_toggle_bypass()
    assert plugin.is_bypassed() is True

    handler.hide_fullscreen_panel()

    _assert_tile_matches_bypass_state(tile, plugin)


def test_plugin_window_bypass_refreshes_grid_tile(v3_system: SystemFixture, make_plugin):
    handler = v3_system.handler
    plugin = _install_plugin(v3_system, make_plugin)
    tile = _tile_for(v3_system, plugin)
    _assert_tile_matches_bypass_state(tile, plugin)

    handler.show_fullscreen_panel(plugin, _DemoWindowPanel)
    panel = cast(_DemoWindowPanel, handler._fullscreen_panel)
    assert panel is not None
    panel._on_toggle_bypass()
    assert plugin.is_bypassed() is True

    handler.hide_fullscreen_panel()

    _assert_tile_matches_bypass_state(tile, plugin)
