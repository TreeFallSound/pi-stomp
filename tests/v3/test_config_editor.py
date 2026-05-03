"""Integration tests for PedalboardConfigEditor on v3 hardware."""

from pathlib import Path

from pistomp.config_overrides import UNSET, load_override
from pistomp.pedalboard_config_editor import COLOR_PALETTE, LONGPRESS_ACTIONS, EditorRow, PedalboardConfigEditor
import pistomp.switchstate as switchstate
from tests.types import SystemFixture
from uilib import InputEvent


def _setup_bundle(v3_system: SystemFixture, tmp_path: Path) -> Path:
    """Point the current pedalboard at a writable tmp directory."""
    bundle_dir = tmp_path / "test.pedalboard"
    bundle_dir.mkdir()
    v3_system.handler.current.pedalboard.bundle = str(bundle_dir)
    return bundle_dir


# ---------------------------------------------------------------------------
# Menu model
# ---------------------------------------------------------------------------


def test_build_menu_model_covers_all_footswitches(v3_system: SystemFixture, tmp_path: Path):
    _setup_bundle(v3_system, tmp_path)
    hw = v3_system.hw
    editor = PedalboardConfigEditor(v3_system.handler, hw, v3_system.handler.lcd)

    rows = editor._build_menu_model()
    fs_rows = [r for r in rows if r.target == "footswitch"]

    assert len(fs_rows) == len(hw.footswitches) * 3
    assert {r.field for r in fs_rows} == {"longpress", "color", "disable"}


def test_build_menu_model_covers_encoders(v3_system: SystemFixture, tmp_path: Path):
    _setup_bundle(v3_system, tmp_path)
    hw = v3_system.hw
    editor = PedalboardConfigEditor(v3_system.handler, hw, v3_system.handler.lcd)

    rows = editor._build_menu_model()
    enc_rows = [r for r in rows if r.target == "encoder"]

    active_encoders = [e for e in hw.encoders if e is not None and getattr(e, "id", None) is not None]
    assert len(enc_rows) == len(active_encoders)
    assert all(r.field == "longpress" for r in enc_rows)


def test_build_menu_model_reflects_existing_override(v3_system: SystemFixture, tmp_path: Path):
    bundle_dir = _setup_bundle(v3_system, tmp_path)
    fs_id = v3_system.hw.footswitches[0].id
    (bundle_dir / "config.yml").write_text(
        f"hardware:\n  footswitches:\n  - id: {fs_id}\n    color: Red\n"
    )
    editor = PedalboardConfigEditor(v3_system.handler, v3_system.hw, v3_system.handler.lcd)

    rows = editor._build_menu_model()
    color_row = next(r for r in rows if r.target == "footswitch" and r.index == fs_id and r.field == "color")
    assert color_row.current_value == "Red"


def test_build_menu_model_no_override_current_value_is_none(v3_system: SystemFixture, tmp_path: Path):
    _setup_bundle(v3_system, tmp_path)
    editor = PedalboardConfigEditor(v3_system.handler, v3_system.hw, v3_system.handler.lcd)

    rows = editor._build_menu_model()
    color_row = next(r for r in rows if r.target == "footswitch" and r.field == "color")
    assert color_row.current_value is None


# ---------------------------------------------------------------------------
# Save behaviour
# ---------------------------------------------------------------------------


def test_on_value_chosen_writes_yaml(v3_system: SystemFixture, tmp_path: Path, snapshot):
    bundle_dir = _setup_bundle(v3_system, tmp_path)
    fs_id = v3_system.hw.footswitches[0].id
    row = EditorRow("footswitch", fs_id, "color", None, None, list(COLOR_PALETTE))
    editor = PedalboardConfigEditor(v3_system.handler, v3_system.hw, v3_system.handler.lcd)

    editor._on_value_chosen((row, "Red"))

    doc = load_override(bundle_dir)
    assert doc is not None
    entry = next(e for e in doc["hardware"]["footswitches"] if e["id"] == fs_id)
    assert entry["color"] == "Red"
    snapshot()


def test_on_value_chosen_disable_coerced_to_bool(v3_system: SystemFixture, tmp_path: Path, snapshot):
    bundle_dir = _setup_bundle(v3_system, tmp_path)
    fs_id = v3_system.hw.footswitches[0].id
    row = EditorRow("footswitch", fs_id, "disable", None, None, ["true", "false"])
    editor = PedalboardConfigEditor(v3_system.handler, v3_system.hw, v3_system.handler.lcd)

    editor._on_value_chosen((row, "true"))

    doc = load_override(bundle_dir)
    assert doc is not None
    entry = next(e for e in doc["hardware"]["footswitches"] if e["id"] == fs_id)
    assert entry["disable"] is True
    snapshot()


def test_on_value_chosen_unset_removes_key(v3_system: SystemFixture, tmp_path: Path, snapshot):
    bundle_dir = _setup_bundle(v3_system, tmp_path)
    fs_id = v3_system.hw.footswitches[0].id
    (bundle_dir / "config.yml").write_text(
        f"hardware:\n  footswitches:\n  - id: {fs_id}\n    color: Red\n"
    )
    row = EditorRow("footswitch", fs_id, "color", "Red", None, list(COLOR_PALETTE))
    editor = PedalboardConfigEditor(v3_system.handler, v3_system.hw, v3_system.handler.lcd)

    editor._on_value_chosen((row, UNSET))

    assert not (bundle_dir / "config.yml").exists()
    snapshot()


def test_on_value_chosen_triggers_hardware_reinit(v3_system: SystemFixture, tmp_path: Path, snapshot):
    bundle_dir = _setup_bundle(v3_system, tmp_path)
    fs_id = v3_system.hw.footswitches[0].id
    row = EditorRow("footswitch", fs_id, "longpress", None, None, list(LONGPRESS_ACTIONS))
    editor = PedalboardConfigEditor(v3_system.handler, v3_system.hw, v3_system.handler.lcd)

    editor._on_value_chosen((row, "next_snapshot"))

    fs = v3_system.hw.footswitches[0]
    assert len(fs.longpress_groups) > 0
    snapshot()


# ---------------------------------------------------------------------------
# Full interaction flow
# ---------------------------------------------------------------------------


def test_config_editor_color_flow(v3_system: SystemFixture, tmp_path: Path, snapshot):
    """Open editor → navigate to FS0 color → pick Red → menu closes, hardware reloads."""
    handler = v3_system.handler
    hw = v3_system.hw
    bundle_dir = _setup_bundle(v3_system, tmp_path)
    fs_id = hw.footswitches[0].id

    # Open config editor via icon click
    handler.lcd.main_panel.sel_widget(handler.lcd.w_config_edit)
    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    snapshot("menu")

    # Step from FS0 longpress (item 0) to FS0 color (item 1) and open picker
    handler.universal_encoder_select(1)
    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    snapshot("color_picker")

    # Step from "(use default: none)" (item 0) to Red (item 1) and confirm
    handler.universal_encoder_select(1)
    handler.universal_encoder_sw(switchstate.Value.RELEASED)
    snapshot("after_save")

    doc = load_override(bundle_dir)
    assert doc is not None
    entry = next(e for e in doc["hardware"]["footswitches"] if e["id"] == fs_id)
    assert entry["color"] == "Red"
