"""Dynamic pedalboard change tests: plugin add/remove and connection connect/disconnect.

These events arrive over WebSocket while a pedalboard is already loaded. pi-stomp
updates its in-memory model and redraws the LCD without triggering a full LILV reload.

The snapshot tests and the epic use the parallel_beths topology:

    capture_1 ──┬── Comp → Amp → Delay ──┐
                ├── OD → Chorus        ──┤→ MixEQ → playback_{1,2}
                └── Gate               ──┘

7 plugins, 3 lanes of depth 3/2/1 + MixEQ merger.  The varying depths exercise
dummy-node insertion and the column-compression DP at a legible scale.
"""

import json
import urllib.parse
from unittest.mock import MagicMock

import pytest

from modalapi.pedalboard import Pedalboard
from tests.types import SystemFixture


# ---------------------------------------------------------------------------
# Plugin metadata stubs for dynamic-add REST responses
# ---------------------------------------------------------------------------

_EXTRA_CHORUS_URI = "http://example.com/extra-chorus"
_EXTRA_CHORUS_INFO = {
    "name": "Extra Chorus",
    "category": ["Modulator"],
    "ports": {
        "control": {
            "input": [
                {"symbol": "rate", "shortName": "Rate", "ranges": {"minimum": 0.0, "maximum": 5.0, "default": 1.0}},
                {"symbol": "depth", "shortName": "Depth", "ranges": {"minimum": 0.0, "maximum": 1.0, "default": 0.5}},
                {"symbol": "mix", "shortName": "Mix", "ranges": {"minimum": 0.0, "maximum": 1.0, "default": 0.7}},
            ]
        }
    },
}

_EXTRA_VERB_URI = "http://example.com/extra-verb"
_EXTRA_VERB_INFO = {
    "name": "Extra Reverb",
    "category": ["Reverb"],
    "ports": {
        "control": {
            "input": [
                {"symbol": "decay", "shortName": "Decay", "ranges": {"minimum": 0.1, "maximum": 10.0, "default": 2.0}},
                {"symbol": "mix", "shortName": "Mix", "ranges": {"minimum": 0.0, "maximum": 1.0, "default": 0.4}},
            ]
        }
    },
}


def _effect_get_side_effect(*info_maps):
    """Return a mock_get side-effect that serves plugin info for effect/get?uri= URLs
    and falls through to sensible defaults for all other URLs."""
    encoded: dict[str, dict] = {}
    for m in info_maps:
        for uri, info in m.items():
            encoded[urllib.parse.quote(uri)] = info

    def side_effect(url, **_kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "effect/get" in url:
            query = url.split("?", 1)[1] if "?" in url else ""
            params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
            requested = params.get("uri", "")
            if requested in encoded:
                resp.text = json.dumps(encoded[requested])
                return resp
        if "pedalboard/list" in url:
            resp.text = json.dumps([])
        elif "snapshot/list" in url:
            resp.text = json.dumps({"0": "Default"})
        elif "snapshot/name" in url:
            resp.text = json.dumps({"name": "Default"})
        else:
            resp.text = "{}"
        return resp

    return side_effect


# ---------------------------------------------------------------------------
# Unit tests: Pedalboard._build_plugin
# ---------------------------------------------------------------------------


def test_build_plugin_creates_plugin():
    pb = Pedalboard("Test", "/test/bundle")
    plugin = pb._build_plugin("ExtraChorus", _EXTRA_CHORUS_URI, 100.0, 50.0, _EXTRA_CHORUS_INFO)
    assert plugin is not None
    assert plugin.instance_id == "ExtraChorus"
    assert plugin.uri == _EXTRA_CHORUS_URI
    assert plugin.canvas_x == 100.0
    assert plugin.canvas_y == 50.0
    assert plugin.category == "Modulator"
    assert plugin.name == "Extra Chorus"


def test_build_plugin_returns_none_for_empty_info():
    pb = Pedalboard("Test", "/test/bundle")
    assert pb._build_plugin("ExtraChorus", _EXTRA_CHORUS_URI, 0.0, 0.0, {}) is None


def test_build_plugin_bypass_param_always_present():
    pb = Pedalboard("Test", "/test/bundle")
    plugin = pb._build_plugin("ExtraChorus", _EXTRA_CHORUS_URI, 0.0, 0.0, _EXTRA_CHORUS_INFO)
    assert plugin is not None
    assert ":bypass" in plugin.parameters
    assert plugin.parameters[":bypass"].value == 0.0


def test_build_plugin_control_ports_use_range_defaults():
    pb = Pedalboard("Test", "/test/bundle")
    plugin = pb._build_plugin("ExtraChorus", _EXTRA_CHORUS_URI, 0.0, 0.0, _EXTRA_CHORUS_INFO)
    assert plugin is not None
    assert plugin.parameters["rate"].value == pytest.approx(1.0)
    assert plugin.parameters["depth"].value == pytest.approx(0.5)
    assert plugin.parameters["mix"].value == pytest.approx(0.7)


def test_build_plugin_no_control_ports_succeeds():
    info = {"name": "Amp", "category": ["Amp"], "ports": {"control": {"input": []}}}
    pb = Pedalboard("Test", "/test/bundle")
    plugin = pb._build_plugin("Amp", "http://example.com/amp", 0.0, 0.0, info)
    assert plugin is not None
    assert list(plugin.parameters.keys()) == [":bypass"]


def test_build_plugin_missing_category_is_none():
    info = {**_EXTRA_CHORUS_INFO}
    info.pop("category", None)
    pb = Pedalboard("Test", "/test/bundle")
    plugin = pb._build_plugin("ExtraChorus", _EXTRA_CHORUS_URI, 0.0, 0.0, info)
    assert plugin is not None
    assert plugin.category is None


# ---------------------------------------------------------------------------
# Unit tests: Pedalboard.add_connection / remove_connection
# ---------------------------------------------------------------------------


def test_add_connection_appends_to_list():
    pb = Pedalboard("Test", "/test/bundle")
    pb.add_connection("/graph/Fuzz/out_L", "/graph/Delay/in_L")
    assert len(pb.connections) == 1
    conn = pb.connections[0]
    assert conn.src.id == "Fuzz"
    assert conn.src.port_symbol == "out_L"
    assert conn.dst.id == "Delay"
    assert conn.dst.port_symbol == "in_L"


def test_add_connection_deduplication():
    pb = Pedalboard("Test", "/test/bundle")
    pb.add_connection("/graph/Fuzz/out_L", "/graph/Delay/in_L")
    pb.add_connection("/graph/Fuzz/out_L", "/graph/Delay/in_L")
    assert len(pb.connections) == 1


def test_add_connection_source_only_no_crash():
    pb = Pedalboard("Test", "/test/bundle")
    pb.add_connection("/graph/capture_1", "/graph/Fuzz/in_L")
    assert len(pb.connections) == 1
    assert pb.connections[0].src.id == "capture_1"


def test_remove_connection_removes_matching():
    pb = Pedalboard("Test", "/test/bundle")
    pb.add_connection("/graph/Fuzz/out_L", "/graph/Delay/in_L")
    pb.add_connection("/graph/Delay/out_L", "/graph/playback_1")
    pb.remove_connection("/graph/Fuzz/out_L", "/graph/Delay/in_L")
    assert len(pb.connections) == 1
    assert pb.connections[0].src.id == "Delay"


def test_remove_connection_unknown_is_noop():
    pb = Pedalboard("Test", "/test/bundle")
    pb.add_connection("/graph/Fuzz/out_L", "/graph/Delay/in_L")
    pb.remove_connection("/graph/Fuzz/out_R", "/graph/Delay/in_R")
    assert len(pb.connections) == 1


def test_remove_connection_empty_list_is_noop():
    pb = Pedalboard("Test", "/test/bundle")
    pb.remove_connection("/graph/Fuzz/out_L", "/graph/Delay/in_L")
    assert pb.connections == []


# ---------------------------------------------------------------------------
# Integration tests: dynamic plugin add
# ---------------------------------------------------------------------------


def test_v3_dynamic_add_creates_plugin_in_model(parallel_beths_system: SystemFixture):
    """inject `add` for unknown instance → REST fetch → plugin appears in pedalboard model."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge
    parallel_beths_system.mock_get.side_effect = _effect_get_side_effect({_EXTRA_CHORUS_URI: _EXTRA_CHORUS_INFO})
    before = len(handler.current.pedalboard.plugins)

    ws_bridge.inject(f"add /graph/ExtraChorus {_EXTRA_CHORUS_URI} 900.0 50.0 0 1 1")
    handler.poll_ws_messages()

    assert len(handler.current.pedalboard.plugins) == before + 1
    added = next(p for p in handler.current.pedalboard.plugins if p.instance_id == "ExtraChorus")
    assert added.uri == _EXTRA_CHORUS_URI
    assert added.canvas_x == 900.0
    assert not added.is_bypassed()


def test_v3_dynamic_add_bypassed_plugin(parallel_beths_system: SystemFixture):
    """bypass field=1 in add message → plugin starts bypassed."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge
    parallel_beths_system.mock_get.side_effect = _effect_get_side_effect({_EXTRA_CHORUS_URI: _EXTRA_CHORUS_INFO})

    ws_bridge.inject(f"add /graph/ExtraChorus {_EXTRA_CHORUS_URI} 900.0 50.0 1 1 1")
    handler.poll_ws_messages()

    added = next(p for p in handler.current.pedalboard.plugins if p.instance_id == "ExtraChorus")
    assert added.is_bypassed()


def test_v3_dynamic_add_preserves_canvas_x_sort_order(parallel_beths_system: SystemFixture):
    """Dynamically added plugin is inserted at the correct canvas-X position in the sorted list."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge
    parallel_beths_system.mock_get.side_effect = _effect_get_side_effect({_EXTRA_CHORUS_URI: _EXTRA_CHORUS_INFO})

    # x=200: should land between col0 (x=100) and col1 (x=300)
    ws_bridge.inject(f"add /graph/ExtraChorus {_EXTRA_CHORUS_URI} 200.0 25.0 0 1 1")
    handler.poll_ws_messages()

    xs = [p.canvas_x for p in handler.current.pedalboard.plugins]
    assert xs == sorted(xs), "plugins must remain sorted by canvas_x after dynamic add"


def test_v3_dynamic_add_known_plugin_updates_bypass_only(parallel_beths_system: SystemFixture):
    """add for a plugin already in the model → bypass update, no second copy inserted."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge
    before = len(handler.current.pedalboard.plugins)

    # Chorus is in the model as bypassed=True from the fixture
    ws_bridge.inject(f"add /graph/Chorus http://anything 300.0 50.0 0 1 1")
    handler.poll_ws_messages()

    assert len(handler.current.pedalboard.plugins) == before
    chorus = next(p for p in handler.current.pedalboard.plugins if p.instance_id == "Chorus")
    assert not chorus.is_bypassed()  # bypass cleared by the add message


def test_v3_dynamic_add_no_metadata_silently_skips(parallel_beths_system: SystemFixture):
    """REST returns {} for unknown URI → no plugin added, existing board untouched."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge
    before = len(handler.current.pedalboard.plugins)

    ws_bridge.inject("add /graph/Unknown http://not.registered/plugin 0.0 0.0 0 1 1")
    handler.poll_ws_messages()

    assert len(handler.current.pedalboard.plugins) == before


def test_v3_dynamic_add_control_port_defaults_populated(parallel_beths_system: SystemFixture):
    """Newly added plugin's control parameters are initialized from REST range defaults."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge
    parallel_beths_system.mock_get.side_effect = _effect_get_side_effect({_EXTRA_CHORUS_URI: _EXTRA_CHORUS_INFO})

    ws_bridge.inject(f"add /graph/ExtraChorus {_EXTRA_CHORUS_URI} 900.0 50.0 0 1 1")
    handler.poll_ws_messages()

    added = next(p for p in handler.current.pedalboard.plugins if p.instance_id == "ExtraChorus")
    assert added.parameters["rate"].value == pytest.approx(1.0)
    assert added.parameters["depth"].value == pytest.approx(0.5)
    assert added.parameters["mix"].value == pytest.approx(0.7)


def test_v3_dynamic_add_param_set_echo_updates_value(parallel_beths_system: SystemFixture):
    """After dynamic add, a param_set echo from mod-ui updates the cached parameter value."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge
    parallel_beths_system.mock_get.side_effect = _effect_get_side_effect({_EXTRA_CHORUS_URI: _EXTRA_CHORUS_INFO})

    ws_bridge.inject(f"add /graph/ExtraChorus {_EXTRA_CHORUS_URI} 900.0 50.0 0 1 1")
    ws_bridge.inject("param_set /graph/ExtraChorus rate 3.5")
    handler.poll_ws_messages()

    added = next(p for p in handler.current.pedalboard.plugins if p.instance_id == "ExtraChorus")
    assert added.parameters["rate"].value == pytest.approx(3.5)


# ---------------------------------------------------------------------------
# Integration tests: dynamic plugin remove
# ---------------------------------------------------------------------------


def test_v3_dynamic_remove_removes_plugin_from_model(parallel_beths_system: SystemFixture):
    """inject `remove` → plugin gone from pedalboard.plugins."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge
    before = len(handler.current.pedalboard.plugins)

    ws_bridge.inject("remove /graph/Chorus")
    handler.poll_ws_messages()

    ids = [p.instance_id for p in handler.current.pedalboard.plugins]
    assert "Chorus" not in ids
    assert len(handler.current.pedalboard.plugins) == before - 1


def test_v3_dynamic_remove_unknown_plugin_is_noop(parallel_beths_system: SystemFixture):
    """remove for an instance not in the model: safe no-op, existing plugins untouched."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge
    before = len(handler.current.pedalboard.plugins)

    ws_bridge.inject("remove /graph/NotHere")
    handler.poll_ws_messages()

    assert len(handler.current.pedalboard.plugins) == before


def test_v3_dynamic_remove_last_plugin_empties_list(v3_system: SystemFixture, make_plugin):
    """remove the only plugin on a minimal board → empty plugins list."""
    handler = v3_system.handler
    ws_bridge = v3_system.ws_bridge
    handler.current.pedalboard.plugins = [make_plugin("Fuzz")]

    ws_bridge.inject("remove /graph/Fuzz")
    handler.poll_ws_messages()

    assert handler.current.pedalboard.plugins == []


def test_v3_dynamic_remove_clears_footswitch_binding(parallel_beths_system: SystemFixture):
    """Removing a bound plugin clears the footswitch binding via rebind."""
    handler = parallel_beths_system.handler
    hw = parallel_beths_system.hw
    ws_bridge = parallel_beths_system.ws_bridge

    # Bind footswitch 0 to Comp's :bypass param, then remove Comp
    fs = hw.footswitches[0]
    binding_key = next(k for k, v in hw.controllers.items() if v is fs)
    comp = next(p for p in handler.current.pedalboard.plugins if p.instance_id == "Comp")
    comp.parameters[":bypass"].binding = binding_key
    handler.bind_current_pedalboard()
    assert fs.parameter is comp.parameters[":bypass"]

    ws_bridge.inject("remove /graph/Comp")
    handler.poll_ws_messages()

    assert fs.parameter is None


# ---------------------------------------------------------------------------
# Integration tests: dynamic connect / disconnect
# ---------------------------------------------------------------------------


def test_v3_dynamic_connect_adds_connection(parallel_beths_system: SystemFixture):
    """inject `connect` → Connection appears in pedalboard.connections."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge
    before = len(handler.current.pedalboard.connections)

    # Cross-lane wire: Delay (lane A col2) back to Gate (lane C col0) — unusual but valid
    ws_bridge.inject("connect /graph/Gate/out /graph/Amp/in")
    handler.poll_ws_messages()

    assert len(handler.current.pedalboard.connections) == before + 1
    last = handler.current.pedalboard.connections[-1]
    assert last.src.id == "Gate"
    assert last.dst.id == "Amp"


def test_v3_dynamic_connect_deduplication(parallel_beths_system: SystemFixture):
    """Injecting the same connect twice doesn't create a duplicate."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge

    ws_bridge.inject("connect /graph/Gate/out /graph/Amp/in")
    ws_bridge.inject("connect /graph/Gate/out /graph/Amp/in")
    handler.poll_ws_messages()

    matching = [c for c in handler.current.pedalboard.connections if c.src.id == "Gate" and c.dst.id == "Amp"]
    assert len(matching) == 1


def test_v3_dynamic_disconnect_removes_connection(parallel_beths_system: SystemFixture):
    """inject `disconnect` → Connection removed from pedalboard.connections."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge

    # Comp → Amp is lane A's first connection
    before = len(handler.current.pedalboard.connections)

    ws_bridge.inject("disconnect /graph/Comp/out /graph/Amp/in")
    handler.poll_ws_messages()

    after = len(handler.current.pedalboard.connections)
    remaining_ids = [(c.src.id, c.dst.id) for c in handler.current.pedalboard.connections]
    assert after == before - 1
    assert ("Comp", "Amp") not in remaining_ids


def test_v3_dynamic_disconnect_unknown_is_noop(parallel_beths_system: SystemFixture):
    """disconnect for a port pair not in the model: safe no-op."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge
    before = len(handler.current.pedalboard.connections)

    ws_bridge.inject("disconnect /graph/Comp/out_R /graph/Gate/in_R")
    handler.poll_ws_messages()

    assert len(handler.current.pedalboard.connections) == before


# ---------------------------------------------------------------------------
# Snapshot tests — layout and LCD reflect model changes
# ---------------------------------------------------------------------------


def test_v3_parallel_beths_initial_layout(parallel_beths_system: SystemFixture, snapshot):
    """Baseline snapshot of the 3-lane + MixEQ layout at board load time."""
    snapshot("loaded")


def test_v3_parallel_beths_add_plugin_lcd(parallel_beths_system: SystemFixture, snapshot):
    """Adding ExtraChorus beyond MixEQ: grid grows a new rightmost column."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge
    parallel_beths_system.mock_get.side_effect = _effect_get_side_effect({_EXTRA_CHORUS_URI: _EXTRA_CHORUS_INFO})

    snapshot("before")
    ws_bridge.inject(f"add /graph/ExtraChorus {_EXTRA_CHORUS_URI} 900.0 50.0 0 1 1")
    handler.poll_ws_messages()
    snapshot("after")


def test_v3_parallel_beths_remove_plugin_lcd(parallel_beths_system: SystemFixture, snapshot):
    """Removing Chorus (lane B col1, bypassed): lane B shortens to depth 1."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge

    snapshot("before")
    ws_bridge.inject("remove /graph/Chorus")
    handler.poll_ws_messages()
    snapshot("after")


def test_v3_parallel_beths_connect_lcd(parallel_beths_system: SystemFixture, snapshot):
    """Cross-lane connection Gate→Amp: new wire appears in the grid."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge

    snapshot("before")
    ws_bridge.inject("connect /graph/Gate/out /graph/Amp/in")
    handler.poll_ws_messages()
    snapshot("after")


def test_v3_parallel_beths_disconnect_lcd(parallel_beths_system: SystemFixture, snapshot):
    """Disconnecting Comp→Amp (lane A first wire): Comp becomes isolated."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge

    snapshot("before")
    ws_bridge.inject("disconnect /graph/Comp/out /graph/Amp/in")
    handler.poll_ws_messages()
    snapshot("after")


# ---------------------------------------------------------------------------
# Epic: multi-edit sequence + navigate selection to dynamically added plugin
# ---------------------------------------------------------------------------


def test_v3_parallel_beths_dynamic_epic(parallel_beths_system: SystemFixture, snapshot, nav_handler):
    """Load a 3-lane board, apply a sequence of WS-driven changes, then navigate
    the encoder selection across the modified grid until it lands on ExtraChorus.

    Layout after all changes (Phase 1–6):

        col0(x=100): Comp(isolated), OD, Gate
        col1(x=300): Amp
        col2(x=500): Delay
        col3(x=700): MixEQ
        col4(x=900): ExtraChorus, ExtraVerb

    Snapshots pin each topology state and the navigation progress.
    """
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge
    parallel_beths_system.mock_get.side_effect = _effect_get_side_effect(
        {_EXTRA_CHORUS_URI: _EXTRA_CHORUS_INFO, _EXTRA_VERB_URI: _EXTRA_VERB_INFO}
    )

    # ── Phase 1: baseline ─────────────────────────────────────────────────────
    snapshot("01_loaded")

    # ── Phase 2: add ExtraChorus after MixEQ ─────────────────────────────────
    ws_bridge.inject(f"add /graph/ExtraChorus {_EXTRA_CHORUS_URI} 900.0 50.0 0 1 1")
    handler.poll_ws_messages()
    assert any(p.instance_id == "ExtraChorus" for p in handler.current.pedalboard.plugins)
    snapshot("02_extrachorus_added")

    # ── Phase 3: wire ExtraChorus into the signal path ────────────────────────
    ws_bridge.inject("connect /graph/MixEQ/out /graph/ExtraChorus/in")
    handler.poll_ws_messages()
    snapshot("03_extrachorus_wired")

    # ── Phase 4: add ExtraVerb alongside ExtraChorus (same column, different row) ──
    ws_bridge.inject(f"add /graph/ExtraVerb {_EXTRA_VERB_URI} 900.0 150.0 0 1 1")
    handler.poll_ws_messages()
    ws_bridge.inject("connect /graph/MixEQ/out_L /graph/ExtraVerb/in")
    handler.poll_ws_messages()
    snapshot("04_extraverb_added_and_wired")

    # ── Phase 5: remove the bypassed Chorus from lane B ──────────────────────
    ws_bridge.inject("remove /graph/Chorus")
    handler.poll_ws_messages()
    assert not any(p.instance_id == "Chorus" for p in handler.current.pedalboard.plugins)
    snapshot("05_chorus_removed")

    # ── Phase 6: break lane A's first connection ──────────────────────────────
    # Comp becomes isolated; the layout keeps it in col0 without downstream routing.
    ws_bridge.inject("disconnect /graph/Comp/out /graph/Amp/in")
    handler.poll_ws_messages()
    snapshot("06_comp_disconnected")

    # ── Phase 7: navigate encoder to ExtraChorus ─────────────────────────────
    # draw_main_panel() resets selection to the wrench.  Selector chain:
    #   wrench → pedalboard title → preset title → [grid tiles in layout order]
    # Grid order is column-major L→R, rows within each column.

    snapshot("07_nav_start_wrench")

    # 3 steps from wrench to first plugin tile
    nav_handler(1)
    nav_handler(1)
    nav_handler(1)
    snapshot("08_nav_first_tile")

    # Advance through col0 (Comp, OD, Gate) + col1 (Amp) + col2 (Delay) = 5 more tiles
    nav_handler(5)
    snapshot("09_nav_mid_grid")

    # Advance to ExtraChorus in col4 (MixEQ at position 6, ExtraChorus at position 7)
    nav_handler(2)
    snapshot("10_nav_extrachorus")

    extra_chorus_tile = next((w for w in handler.lcd.w_plugins if w.object.instance_id == "ExtraChorus"), None)
    assert extra_chorus_tile is not None, "ExtraChorus tile must be present in the rendered grid"


# ---------------------------------------------------------------------------
# Blend mode + dynamic mutations
# ---------------------------------------------------------------------------


def _fake_diff_maps(*instance_ids: str) -> list[dict]:
    """Build a minimal segment_diff_maps list with one segment covering all ids."""
    from blend.types import ParamData
    from modalapi.parameter import Type as ParameterType

    segment: dict = {
        iid: {"Tone": ParamData(val_a=0.0, val_b=1.0, param_type=ParameterType.DEFAULT)} for iid in instance_ids
    }
    return [segment]


def test_v3_blend_dynamic_add_shows_on_lcd_and_leaves_diff_maps_intact(
    parallel_beths_system: SystemFixture,
):
    """Dynamic add with blend active: LCD updates; diff maps are not modified
    (new plugin absent from snapshot data, so blend ignores it)."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge
    parallel_beths_system.mock_get.side_effect = _effect_get_side_effect({_EXTRA_CHORUS_URI: _EXTRA_CHORUS_INFO})

    blend = MagicMock()
    blend.segment_diff_maps = _fake_diff_maps("Comp", "Amp")
    handler.blend_modes = {"Blend": blend}
    try:
        before = len(handler.current.pedalboard.plugins)
        ws_bridge.inject(f"add /graph/ExtraChorus {_EXTRA_CHORUS_URI} 900.0 50.0 0 1 1")
        handler.poll_ws_messages()

        assert len(handler.current.pedalboard.plugins) == before + 1, "plugin must appear in model"
        assert any(p.instance_id == "ExtraChorus" for p in handler.current.pedalboard.plugins)
        # diff maps untouched — ExtraChorus absent from snapshots, blend ignores it
        assert "Comp" in blend.segment_diff_maps[0]
        assert "ExtraChorus" not in blend.segment_diff_maps[0]
    finally:
        handler.blend_modes = {}


def test_v3_blend_dynamic_remove_strips_instance_from_diff_maps(
    parallel_beths_system: SystemFixture,
):
    """Dynamic remove with blend active: removed plugin purged from every segment diff map."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge

    blend = MagicMock()
    blend.segment_diff_maps = _fake_diff_maps("Comp", "Amp", "Gate")
    handler.blend_modes = {"Blend": blend}
    try:
        ws_bridge.inject("remove /graph/Comp")
        handler.poll_ws_messages()

        assert "Comp" not in blend.segment_diff_maps[0], "removed plugin must be purged from diff map"
        assert "Amp" in blend.segment_diff_maps[0], "unrelated entries must be preserved"
        assert "Gate" in blend.segment_diff_maps[0]
    finally:
        handler.blend_modes = {}


@pytest.mark.skip(
    reason=(
        "Known gap: re-adding a plugin after removal does not restore it to the blend diff maps. "
        "The plugin was stripped from diff_maps on remove; dynamic add intentionally skips diff-map "
        "insertion (the plugin was never in the stop snapshots). Blend only recovers after the user "
        "saves a snapshot in MOD-UI, causing check_for_snapshot_changes() to trigger a full re-prepare. "
        "Remove this skip once we implement re-prepare-on-add when blend is active."
    )
)
def test_v3_blend_readd_after_remove_restores_diff_maps(
    parallel_beths_system: SystemFixture,
):
    """After remove then re-add of the same plugin, blend diff maps should cover it again.
    Currently fails: we strip on remove but don't re-prepare on add."""
    handler = parallel_beths_system.handler
    ws_bridge = parallel_beths_system.ws_bridge
    parallel_beths_system.mock_get.side_effect = _effect_get_side_effect({_EXTRA_CHORUS_URI: _EXTRA_CHORUS_INFO})

    blend = MagicMock()
    blend.segment_diff_maps = _fake_diff_maps("ExtraChorus")
    handler.blend_modes = {"Blend": blend}
    try:
        # Remove ExtraChorus first — diff maps stripped
        ws_bridge.inject(f"add /graph/ExtraChorus {_EXTRA_CHORUS_URI} 900.0 50.0 0 1 1")
        handler.poll_ws_messages()
        ws_bridge.inject("remove /graph/ExtraChorus")
        handler.poll_ws_messages()
        assert "ExtraChorus" not in blend.segment_diff_maps[0]

        # Re-add the same plugin
        ws_bridge.inject(f"add /graph/ExtraChorus {_EXTRA_CHORUS_URI} 900.0 50.0 0 1 1")
        handler.poll_ws_messages()

        # This assertion currently fails: the re-added plugin is not in the diff maps
        assert "ExtraChorus" in blend.segment_diff_maps[0], (
            "re-added plugin should be in diff maps (requires re-prepare)"
        )
    finally:
        handler.blend_modes = {}
