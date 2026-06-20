"""v3-specific fixtures — delegates stack construction to integration/conftest."""

import json
import time as _time
from collections.abc import Generator
from typing import cast
from unittest.mock import MagicMock

import pytest
import yaml

import common.token as Token
from emulator.controls import MockAnalogControl
from modalapi.wifi import SavedConnection, ScannedNetwork
from tests.conftest import FakeWebSocketBridge
from tests.integration.conftest import _v3_stack
from tests.types import SystemFixture
from ui.wifi_menu import _PassphraseEditor
from uilib.misc import InputEvent
from uilib.text import LetterSelector, TextEditor


@pytest.fixture
def v3_system(fake_lcd, tmp_path) -> Generator[SystemFixture, None, None]:
    yield from _v3_stack(fake_lcd, tmp_path)


# ---------------------------------------------------------------------------
# Parallel Beths fixture — 3-lane + MixEQ complex pedalboard
# ---------------------------------------------------------------------------
#
# Mirrors pedalboard_fixtures.parallel_beths() topology using real Plugin/
# Parameter objects so the full modhandler + LCD code path is exercised.
#
# Lane topology (3 lanes of depth 3/2/1, all lanes feed MixEQ):
#
#   capture_1 ──┬── Comp → Amp → Delay ──┐
#               ├── OD → Chorus          ──┤→ MixEQ → playback
#               └── Gate                 ──┘
#
# Canvas positions:  col0=x100, col1=x300, col2=x500, MixEQ=x700
#                    lane A=y0, lane B=y50, lane C=y100
#
_PARALLEL_BETHS_LANES: list[list[tuple[str, str, bool]]] = [
    # (instance_id, category, bypassed)
    [("Comp",   "Dynamics",   False), ("Amp",    "Amplifier", False), ("Delay",  "Delay",    False)],
    [("OD",     "Distortion", False), ("Chorus", "Modulator", True)],
    [("Gate",   "Dynamics",   False)],
]


def _build_parallel_beths(make_plugin):
    """Build (plugins, connections) for the parallel_beths topology using real Plugin objects."""
    from modalapi.connections import Connection, Endpoint, EndpointKind

    def _ep(kind, id_, port_symbol="", port_idx=0):
        return Endpoint(kind=kind, id=id_, port_symbol=port_symbol, port_idx=port_idx)

    lane_plugins = []
    canvas_y = 0.0
    for lane in _PARALLEL_BETHS_LANES:
        row = []
        canvas_x = 100.0
        for iid, cat, byp in lane:
            p = make_plugin(iid, category=cat, bypassed=byp)
            p.canvas_x = canvas_x
            p.canvas_y = canvas_y
            row.append(p)
            canvas_x += 200.0
        lane_plugins.append(row)
        canvas_y += 50.0

    mix_eq = make_plugin("MixEQ", category="EQ", bypassed=False)
    mix_eq.canvas_x = 700.0
    mix_eq.canvas_y = 50.0

    all_plugins = sorted(
        [p for lane in lane_plugins for p in lane] + [mix_eq],
        key=lambda p: (p.canvas_x, p.canvas_y, p.instance_id),
    )

    conns = []
    for lane in lane_plugins:
        ids = [p.instance_id for p in lane]
        conns.append(Connection(
            src=_ep(EndpointKind.SOURCE, "capture_1", port_symbol="out"),
            dst=_ep(EndpointKind.PLUGIN, ids[0], port_symbol="in"),
        ))
        for a, b in zip(ids, ids[1:]):
            conns.append(Connection(
                src=_ep(EndpointKind.PLUGIN, a, port_symbol="out"),
                dst=_ep(EndpointKind.PLUGIN, b, port_symbol="in"),
            ))
        conns.append(Connection(
            src=_ep(EndpointKind.PLUGIN, ids[-1], port_symbol="out"),
            dst=_ep(EndpointKind.PLUGIN, "MixEQ", port_symbol="in"),
        ))
    conns.append(Connection(
        src=_ep(EndpointKind.PLUGIN, "MixEQ", port_symbol="out"),
        dst=_ep(EndpointKind.SINK, "playback_1", port_symbol="in"),
    ))
    conns.append(Connection(
        src=_ep(EndpointKind.PLUGIN, "MixEQ", port_symbol="out"),
        dst=_ep(EndpointKind.SINK, "playback_2", port_symbol="in"),
    ))

    return all_plugins, conns


@pytest.fixture
def parallel_beths_system(v3_system: SystemFixture, make_plugin) -> SystemFixture:
    """v3 stack with the 5×4 + FinalEQ parallel_beths topology pre-loaded and drawn."""
    handler = v3_system.handler
    hw = v3_system.hw

    plugins, connections = _build_parallel_beths(make_plugin)
    assert handler.current is not None
    handler.current.pedalboard.plugins = plugins
    handler.current.pedalboard.connections = connections
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()

    return v3_system


# ---------------------------------------------------------------------------
# Blend mode fixture
# ---------------------------------------------------------------------------

# Two stops: Clean (Tone=0.2, Level=0.5) and Lead (Tone=0.8, Level=0.9).
# Both stops have bypassed=False so :bypass is constant (not in the diff map).
_BLEND_SNAPSHOTS = {
    "current": 0,
    "snapshots": [
        {
            "name": "Clean",
            "data": {
                "BigMuff": {"bypassed": False, "ports": {"Tone": 0.2, "Level": 0.5}, "preset": "", "parameters": {}},
            },
        },
        {
            "name": "Lead",
            "data": {
                "BigMuff": {"bypassed": False, "ports": {"Tone": 0.8, "Level": 0.9}, "preset": "", "parameters": {}},
            },
        },
    ],
}

_BLEND_CONFIG = {
    "blend_snapshots": [
        {
            "name": "Blend",
            "input_id": 1,  # encoder id=1 exists in the default v3 config
            "interpolation": "linear",
            "stops": ["Clean", "Lead"],
        }
    ]
}

_BLEND_CONFIG_EXP = {
    "blend_snapshots": [
        {
            "name": "Blend",
            "input_id": 0,  # expression pedal
            "interpolation": "linear",
            "stops": ["Clean", "Lead"],
        }
    ]
}


def _build_blend_system(
    v3_system: SystemFixture,
    tmp_path,
    make_plugin,
    make_parameter,
    blend_config: dict,
    bundle_name: str,
    pre_setup=None,
) -> SystemFixture:
    """
    Shared setup for blend-mode fixtures.

    pre_setup(hw) is called before the pedalboard loads — use it to inject
    hardware controls (e.g. a MockAnalogControl for the expression pedal).
    """
    handler = v3_system.handler
    hw = v3_system.hw
    mock_get = v3_system.mock_get

    if pre_setup:
        pre_setup(hw)

    bundle_dir = tmp_path / bundle_name
    bundle_dir.mkdir()
    (bundle_dir / "snapshots.json").write_text(json.dumps(_BLEND_SNAPSHOTS))
    (bundle_dir / "config.yml").write_text(yaml.dump(blend_config))

    def get_side_effect(url, **_kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "pedalboard/list" in url:
            resp.text = json.dumps(
                [
                    {Token.TITLE: "Blend Rig", Token.BUNDLE: str(bundle_dir)},
                    {Token.TITLE: "New Rig", Token.BUNDLE: "/path/to/new.pedalboard"},
                ]
            )
        elif "snapshot/list" in url:
            resp.text = json.dumps({"0": "Clean", "1": "Lead", "2": "Blend"})
        elif "snapshot/name" in url:
            resp.text = json.dumps({"name": "Clean"})
        else:
            resp.text = "{}"
        return resp

    mock_get.side_effect = get_side_effect

    big_muff = make_plugin(
        "/BigMuff",
        category="Distortion",
        parameters={
            "Tone": make_parameter("Tone", "/BigMuff", value=0.2),
            "Level": make_parameter("Level", "/BigMuff", value=0.5),
        },
    )

    pb = handler.pedalboards["/path/to/rig.pedalboard"]
    pb.bundle = str(bundle_dir)
    pb.plugins = [big_muff]

    handler.set_current_pedalboard(pb)

    cast(FakeWebSocketBridge, handler.ws_bridge).sent.clear()
    if handler.active_blend_mode and handler.active_blend_mode.parameter_setter:
        handler.active_blend_mode.parameter_setter.reset_tracking()

    return SystemFixture(handler, hw, v3_system.lcd, mock_get, v3_system.mock_post, v3_system.ws_bridge)


@pytest.fixture
def blend_system(
    v3_system: SystemFixture, tmp_path, make_plugin, make_parameter
) -> Generator[SystemFixture, None, None]:
    """v3 stack with blend mode on encoder id=1."""
    yield _build_blend_system(v3_system, tmp_path, make_plugin, make_parameter, _BLEND_CONFIG, "blend_rig.pedalboard")


@pytest.fixture
def blend_system_exp(
    v3_system: SystemFixture, tmp_path, make_plugin, make_parameter
) -> Generator[SystemFixture, None, None]:
    """v3 stack with blend mode on expression pedal (id=0, last_read=512 ≈ 50%)."""

    def _add_exp_pedal(hw):
        exp_pedal = MockAnalogControl(
            midi_CC=75,
            midi_channel=0,
            midiout=None,
            control_type=Token.EXPRESSION,
            id=0,
        )
        exp_pedal.last_read = 512
        hw.analog_controls.append(exp_pedal)

    yield _build_blend_system(
        v3_system,
        tmp_path,
        make_plugin,
        make_parameter,
        _BLEND_CONFIG_EXP,
        "blend_rig_exp.pedalboard",
        pre_setup=_add_exp_pedal,
    )


# ---------------------------------------------------------------------------
# WiFi test helpers
# ---------------------------------------------------------------------------


def make_scanned(ssid: str, signal: int = 60, security: str = "WPA2", in_use: bool = False) -> ScannedNetwork:
    return ScannedNetwork(ssid=ssid, signal=signal, security=security, in_use=in_use)


def make_saved(ssid: str, name: str | None = None, timestamp: int | None = None) -> SavedConnection:
    return SavedConnection(
        name=name or ssid,
        ssid=ssid,
        timestamp=timestamp if timestamp is not None else int(_time.time()) - 3600,
    )


@pytest.fixture
def wifi_state(v3_system):
    """Configure wifi_manager mock and wifi_status in one call.

    active is the connection *name* (matches SavedConnection.name).

    Also installs an inline CommandQueue shim: submit/submit_scan run the
    command synchronously and invoke the callback immediately, so tests
    don't need to drive a poll loop.
    """

    def _set(scanned=(), saved=(), active=None, hotspot=False, supported=True):
        wm = v3_system.handler.wifi_manager
        wm.scan_networks.return_value = list(scanned)
        wm.list_connections.return_value = list(saved)
        wm.get_cached_saved.return_value = list(saved)

        def _run_inline(cmd, on_done):
            try:
                result = cmd.run(wm)
            except Exception as e:
                result = e
            on_done(result)
            return True

        wm.queue.submit.side_effect = _run_inline
        wm.queue.submit_scan.side_effect = _run_inline
        wm.queue.pending_op_count.return_value = 0

        status = {
            "wifi_supported": supported,
            "wifi_connected": active is not None,
            "hotspot_active": hotspot,
            "ssid": active,
            "connection": active,
        }
        v3_system.handler.wifi_status = status

    return _set


@pytest.fixture
def type_in_editor():
    """Type text into the active TextEditor / _PassphraseEditor via the LetterSelector.

    Returns a ``type(lcd, text)`` helper that, for each character, switches the
    selector into the matching charset mode (via long-click) and clicks it.
    """

    def _type_char(lcd, ch):
        editor = lcd.pstack.current
        assert isinstance(editor, (TextEditor, _PassphraseEditor)), type(editor)
        assert editor.sel_ref is not None
        selector = editor.sel_ref
        assert isinstance(selector, LetterSelector)

        for mode_idx, charset in enumerate(LetterSelector.charsets):
            if ch in charset:
                break
        else:
            raise ValueError(f"character {ch!r} not found in any charset")

        steps = (mode_idx - selector.mode) % len(LetterSelector.charsets)
        if steps:
            selector.l_idx = 3  # a non-control char: long-click cycles the charset
            for _ in range(steps):
                lcd.pstack.input_event(InputEvent.LONG_CLICK)

        selector.l_idx = charset.index(ch)
        lcd.pstack.input_event(InputEvent.CLICK)

    def _type(lcd, text):
        for ch in text:
            _type_char(lcd, ch)

    return _type


# ---------------------------------------------------------------------------
# Nav-encoder fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def nav_lcd(v3_system):
    """nav_lcd(d) — step the LCD nav selector by ``d`` detents, then poll.

    Mirrors the main loop's step-then-poll: enc_step advances the selector
    (small clips push inline), poll_updates ticks dialogs and flushes any
    coalesced large clips.
    """
    lcd = v3_system.handler._lcd

    def _nav(d: int) -> None:
        lcd.enc_step(d)
        lcd.poll_updates()

    return _nav


@pytest.fixture
def nav_handler(v3_system):
    """nav_handler(d) — step the handler nav selector by ``d`` detents, then poll.

    Mirrors the main loop's step-then-poll: universal_encoder_select advances
    the selector via the LCD, poll_lcd_updates ticks dialogs and flushes any
    coalesced large clips (e.g. the EQ curve).
    """
    handler = v3_system.handler

    def _nav(d: int) -> None:
        handler.universal_encoder_select(d)
        handler.poll_lcd_updates()

    return _nav
