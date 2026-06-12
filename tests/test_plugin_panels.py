"""Tests for the generic plugin-panel infrastructure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pytest

from common.parameter import Parameter
from modalapi.plugin import Plugin
from plugins import PANELS, register_panel
from plugins.base import PluginPanel
from pistomp.input.event import EncoderEvent, SwitchEvent, SwitchEventKind
from uilib.box import Box
from uilib.panel import PanelStack


# ── minimal fake infrastructure ─────────────────────────────────────────────


class FakeWsBridge:
    def __init__(self):
        self.sent: list[tuple[str, str, float]] = []

    def send_parameter(self, instance_id: str, symbol: str, value: float) -> bool:
        self.sent.append((instance_id, symbol, value))
        return True


class FakeHandler:
    def __init__(self):
        self.ws_bridge = FakeWsBridge()
        self.locked: set[tuple[str, str]] = set()

    def is_symbol_locked(self, instance_id: str, symbol: str) -> bool:
        return (instance_id, symbol) in self.locked


# ── minimal concrete panel ───────────────────────────────────────────────────


@dataclass
class DemoState:
    gain: float = 0.0


@register_panel("http://example.com/demo")
class DemoPanel(PluginPanel[DemoState]):
    def snapshot_state(self) -> DemoState:
        p = self.plugin.parameters.get("gain")
        return DemoState(gain=float(p.value) if p else 0.0)

    def apply_state(self, state: DemoState) -> None:
        pass  # no widgets to update in this minimal test

    def build_widgets(self) -> None:
        pass  # chrome only for the minimal test

    def on_encoder_rotation(self, encoder_id: int, rotations: int) -> bool:
        if encoder_id == 1:
            self.set_param("gain", self.plugin.parameters["gain"].value + rotations * 0.1)
            return True
        return False


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_plugin():
    param = Parameter(
        {"name": "Gain", "symbol": "gain", "ranges": {"minimum": 0, "maximum": 10}},
        5.0,
        None,
    )
    p = Plugin(
        instance_id="/pedalboard/demo",
        parameters={"gain": param, ":bypass": Parameter({"name": "bypass", "symbol": ":bypass", "ranges": {"minimum": 0, "maximum": 1}}, 0.0, None)},
        info={},
        category="Utility",
        uri="http://example.com/demo",
    )
    # pedalboard_snapshot set by parser in real life; simulate here
    # Note: Plugin.__init__ strips leading '/' from instance_id
    p.pedalboard_snapshot = {"gain": 5.0}
    return p


@pytest.fixture
def fake_handler():
    return FakeHandler()


# ── registry tests ────────────────────────────────────────────────────────────


class TestRegistry:
    def test_register_panel_populates_dict(self):
        assert "http://example.com/demo" in PANELS
        assert PANELS["http://example.com/demo"] is DemoPanel


# ── base-class tests ────────────────────────────────────────────────────────


class TestPluginPanel:
    def test_construction_sets_up_chrome(self, fake_plugin, fake_handler):
        panel = DemoPanel(plugin=fake_plugin, handler=fake_handler, on_dismiss=lambda: None)
        assert panel._btn_back is not None
        assert panel._btn_bypass is not None
        assert panel._btn_reset is not None
        # Chrome is appended last so it's always navigable
        assert panel.sel_list[-3] is panel._btn_back
        assert panel.sel_list[-2] is panel._btn_bypass
        assert panel.sel_list[-1] is panel._btn_reset

    def test_set_param_queues_and_updates_local(self, fake_plugin, fake_handler):
        panel = DemoPanel(plugin=fake_plugin, handler=fake_handler, on_dismiss=lambda: None)
        panel.set_param("gain", 7.0)
        assert fake_plugin.parameters["gain"].value == 7.0
        assert panel._param_queue == {"gain": 7.0}

    def test_tick_flushes_queue(self, fake_plugin, fake_handler):
        panel = DemoPanel(plugin=fake_plugin, handler=fake_handler, on_dismiss=lambda: None)
        panel.set_param("gain", 7.0)
        panel.tick()
        assert panel._param_queue == {}
        assert fake_handler.ws_bridge.sent == [("pedalboard/demo", "gain", 7.0)]

    def test_handle_encoder_returns_true_when_consumed(self, fake_plugin, fake_handler):
        panel = DemoPanel(plugin=fake_plugin, handler=fake_handler, on_dismiss=lambda: None)
        evt = EncoderEvent(controller=_FakeEnc(id=1), rotations=2)
        assert panel.handle(evt) is True
        assert fake_plugin.parameters["gain"].value == pytest.approx(5.2)

    def test_handle_encoder_returns_false_for_unclaimed_id(self, fake_plugin, fake_handler):
        panel = DemoPanel(plugin=fake_plugin, handler=fake_handler, on_dismiss=lambda: None)
        evt = EncoderEvent(controller=_FakeEnc(id=2), rotations=2)
        assert panel.handle(evt) is False

    def test_handle_non_encoder_returns_false(self, fake_plugin, fake_handler):
        panel = DemoPanel(plugin=fake_plugin, handler=fake_handler, on_dismiss=lambda: None)
        evt = SwitchEvent(controller=_FakeEnc(id=1), kind=SwitchEventKind.PRESS)
        assert panel.handle(evt) is False

    def test_reset_restores_snapshot_and_flushes(self, fake_plugin, fake_handler):
        panel = DemoPanel(plugin=fake_plugin, handler=fake_handler, on_dismiss=lambda: None)
        panel.set_param("gain", 9.0)
        panel.tick()
        fake_handler.ws_bridge.sent.clear()
        panel._on_reset()
        assert fake_plugin.parameters["gain"].value == 5.0
        assert fake_handler.ws_bridge.sent == [("pedalboard/demo", "gain", 5.0)]

    def test_reset_skips_locked_symbols(self, fake_plugin, fake_handler):
        fake_handler.locked = {("pedalboard/demo", "gain")}
        panel = DemoPanel(plugin=fake_plugin, handler=fake_handler, on_dismiss=lambda: None)
        panel.set_param("gain", 9.0)
        panel.tick()
        fake_handler.ws_bridge.sent.clear()
        panel._on_reset()
        # gain is locked, so it should stay at the tweaked value
        assert fake_plugin.parameters["gain"].value == 9.0
        assert fake_handler.ws_bridge.sent == []

    def test_bypass_toggles_and_sends_ws(self, fake_plugin, fake_handler):
        panel = DemoPanel(plugin=fake_plugin, handler=fake_handler, on_dismiss=lambda: None)
        assert fake_plugin.is_bypassed() is False
        panel._on_toggle_bypass()
        assert fake_plugin.is_bypassed() is True
        assert ("pedalboard/demo", ":bypass", 1.0) in fake_handler.ws_bridge.sent


class _FakeEnc:
    def __init__(self, id: int = 0):
        self.id = id
