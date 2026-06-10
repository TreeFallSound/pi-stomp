"""
Parametrized stack fixtures for cross-version integration tests.

  modhandler_system  — Modhandler-based hardware (v2, v3).
  any_system         — all hardware versions.  Add here when v1 (Mod) is ready.
"""

import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml
from PIL import Image

from tests.conftest import FakeWebSocketBridge
from tests.types import SystemFixture, SystemFixtureLegacy
import common.token as Token

PROJECT_ROOT = Path(__file__).parent.parent.parent

with patch("pistomp.settings.Settings.load_settings"), patch("pistomp.settings.Settings.set_setting"):
    from modalapi.modhandler import Modhandler
    from modalapi.mod import Mod
    from pistomp.hardware import Hardware
    from pistomp.pistomp import Pistomp
    from pistomp.pistompcore import Pistompcore
    from pistomp.pistomptre import Pistomptre


# ---------------------------------------------------------------------------
# FakeMonoLcd — captures the gfxhat pixel buffer that lcdgfx.Lcd pushes
# ---------------------------------------------------------------------------


class FakeMonoLcd:
    """Stand-in for the gfxhat lcd module. lcdgfx.Lcd draws into its own PIL
    images then pushes pixels here via set_pixel/show. Each show() snapshots
    the current buffer into an L-mode frame."""

    WIDTH = 128
    HEIGHT = 64

    def __init__(self):
        self._buf = Image.new("L", (self.WIDTH, self.HEIGHT))
        self.frames: list[Image.Image] = []

    def dimensions(self):
        return (self.WIDTH, self.HEIGHT)

    def set_pixel(self, x, y, value):
        if 0 <= x < self.WIDTH and 0 <= y < self.HEIGHT:
            self._buf.putpixel((x, y), 255 if value else 0)

    def show(self):
        # lcdgfx flips coordinates for the upside-down panel; un-rotate for readable baselines.
        self.frames.append(self._buf.copy().transpose(Image.Transpose.ROTATE_180))

    def clear(self):
        self._buf.paste(0, (0, 0, self.WIDTH, self.HEIGHT))


# ---------------------------------------------------------------------------
# Shared stack builder
# ---------------------------------------------------------------------------


def _build_stack(hw_class: type[Hardware], cfg_path: Path, fake_lcd, tmp_path) -> Generator[SystemFixture, None, None]:
    cwd = str(PROJECT_ROOT)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "last.json").write_text(json.dumps({"pedalboard": "/path/to/rig.pedalboard"}))

    Modhandler._Modhandler__single = None  # pyright: ignore[reportAttributeAccessIssue]
    hw_class.__dict__  # ensure class is loaded before mangling
    singleton_attr = f"_{hw_class.__name__}__single"
    setattr(hw_class, singleton_attr, None)

    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    fake_bridge = FakeWebSocketBridge()

    with (
        patch("requests.get") as mock_get,
        patch("requests.post") as mock_post,
        patch("pistomp.settings.Settings") as mock_settings_cls,
        patch("modalapi.pedalboard.Pedalboard.load_bundle"),
        patch("modalapi.wifi.WifiManager") as mock_wm_cls,
        patch("subprocess.check_output", return_value=b"SystemState=running"),
        patch("pistomp.lcd320x240.LcdIli9341", return_value=fake_lcd),
        patch("modalapi.modhandler.AsyncWebSocketBridge", return_value=fake_bridge),
    ):
        # Tests don't drive a poll loop, so stub pending_op_count to always return 0 (no pending ops).
        mock_wm_cls.return_value.queue.pending_op_count.return_value = 0

        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "pedalboard/list" in url:
                resp.text = json.dumps(
                    [
                        {Token.TITLE: "Integration Rig", Token.BUNDLE: "/path/to/rig.pedalboard"},
                        {Token.TITLE: "New Rig", Token.BUNDLE: "/path/to/new.pedalboard"},
                    ]
                )
            elif "snapshot/list" in url:
                resp.text = json.dumps({"0": "Clean", "1": "Lead"})
            elif "snapshot/name" in url:
                resp.text = json.dumps({"name": "Clean"})
            else:
                resp.text = "{}"
            return resp

        mock_get.side_effect = get_side_effect

        def post_side_effect(*args, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = "{}"
            return resp

        mock_post.side_effect = post_side_effect

        mock_settings_cls.return_value.get_setting.return_value = None

        mock_audiocard = MagicMock()
        mock_audiocard.get_volume_parameter.return_value = 0.0
        handler = Modhandler(mock_audiocard, cwd, data_dir=str(data_dir))
        handler.settings.get_setting.return_value = None

        midiout = MagicMock()
        hw = hw_class(cfg, handler, midiout, handler.update_lcd_fs)
        handler.add_hardware(hw)
        handler.load_pedalboards()

        pb = handler.pedalboards["/path/to/rig.pedalboard"]
        pb.plugins = []
        handler.set_current_pedalboard(pb)
        handler.pedalboards["/path/to/new.pedalboard"].plugins = []

        mock_get.reset_mock()
        mock_get.side_effect = get_side_effect
        mock_post.reset_mock()
        mock_post.side_effect = post_side_effect

        yield SystemFixture(handler, hw, fake_lcd, mock_get, mock_post, fake_bridge)


# ---------------------------------------------------------------------------
# Per-version stack builders
# ---------------------------------------------------------------------------


def _v2_stack(fake_lcd, tmp_path) -> Generator[SystemFixture, None, None]:
    cfg_path = PROJECT_ROOT / "setup" / "config_templates" / "default_config_pistompcore.yml"
    yield from _build_stack(Pistompcore, cfg_path, fake_lcd, tmp_path)


def _v3_stack(fake_lcd, tmp_path) -> Generator[SystemFixture, None, None]:
    cfg_path = PROJECT_ROOT / "setup" / "config_templates" / "default_config_pistomptre.yml"
    yield from _build_stack(Pistomptre, cfg_path, fake_lcd, tmp_path)


# ---------------------------------------------------------------------------
# v1 stack — Mod handler + Pistomp hardware + monochrome lcdgfx LCD
# ---------------------------------------------------------------------------


def _v1_stack(tmp_path) -> Generator[SystemFixtureLegacy, None, None]:
    """Real Mod + Pistomp stack. The mono LCD's frames are captured via
    FakeMonoLcd (returned as lcd, exposing .frames like FakeLcd)."""
    cwd = str(PROJECT_ROOT)
    cfg_path = PROJECT_ROOT / "setup" / "config_templates" / "default_config_pistomp.yml"

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    last_json = data_dir / "last.json"
    last_json.write_text(json.dumps({"pedalboard": "/path/to/rig.pedalboard"}))

    from pistomp.lcdgfx import Lcd as MonoLcd

    Mod._Mod__single = None  # pyright: ignore[reportAttributeAccessIssue]
    Pistomp._Pistomp__single = None  # pyright: ignore[reportAttributeAccessIssue]
    setattr(MonoLcd, "_Lcd__single", None)

    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    fake_bridge = FakeWebSocketBridge()
    fake_dev = FakeMonoLcd()

    # Inject a real lcdgfx.Lcd backed by the capturing fake device. Patching the
    # module-level Lcd would break its internal __single self-reference, so we
    # override init_lcd instead.
    def fake_init_lcd(hw_self):
        hw_self.mod.add_lcd(MonoLcd(hw_self.mod.homedir, lcd=fake_dev, backlight=MagicMock(), touch=MagicMock()))

    with (
        patch("requests.get") as mock_get,
        patch("requests.post") as mock_post,
        patch("modalapi.pedalboard.Pedalboard.load_bundle"),
        patch("modalapi.wifi.WifiManager") as mock_wm_cls,
        patch("modalapi.mod.AsyncWebSocketBridge", return_value=fake_bridge),
        patch("modalapi.mod.ExternalMidi.ExternalMidiManager"),
        patch("pistomp.hardware.Hardware.init_spi"),
        patch("pistomp.pistomp.Pistomp.run_test"),
        patch("pistomp.pistomp.Pistomp.init_lcd", fake_init_lcd),
    ):
        mock_wm_cls.return_value.queue.pending_op_count.return_value = 0

        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "pedalboard/list" in url:
                resp.text = json.dumps(
                    [
                        {Token.TITLE: "Integration Rig", Token.BUNDLE: "/path/to/rig.pedalboard"},
                        {Token.TITLE: "New Rig", Token.BUNDLE: "/path/to/new.pedalboard"},
                    ]
                )
            elif "snapshot/list" in url:
                resp.text = json.dumps({"0": "Clean", "1": "Lead"})
            elif "snapshot/name" in url:
                resp.text = json.dumps({"name": "Clean"})
            else:
                resp.text = "{}"
            return resp

        mock_get.side_effect = get_side_effect

        def post_side_effect(*args, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = "{}"
            return resp

        mock_post.side_effect = post_side_effect

        mock_audiocard = MagicMock()
        mock_audiocard.get_volume_parameter.return_value = 0.0
        handler = Mod(mock_audiocard, cwd)
        handler.data_dir = str(data_dir)
        handler.last_json_monitor.path = str(last_json)

        midiout = MagicMock()
        hw = Pistomp(cfg, handler, midiout, handler.update_lcd_fs)
        handler.add_hardware(hw)
        handler.load_pedalboards()

        pb = handler.pedalboards["/path/to/rig.pedalboard"]
        pb.plugins = []
        handler.set_current_pedalboard(pb)
        handler.pedalboards["/path/to/new.pedalboard"].plugins = []

        mock_get.reset_mock()
        mock_get.side_effect = get_side_effect
        mock_post.reset_mock()
        mock_post.side_effect = post_side_effect

        yield SystemFixtureLegacy(handler, hw, fake_dev, mock_get, mock_post, fake_bridge)


_BUILDERS = {
    "v2": _v2_stack,
    "v3": _v3_stack,
}


# ---------------------------------------------------------------------------
# Parametrized fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(params=["v2", "v3"])
def modhandler_system(request, fake_lcd, tmp_path) -> Generator[SystemFixture, None, None]:
    """Full Modhandler + hardware stack, parametrized across supported versions."""
    yield from _BUILDERS[request.param](fake_lcd, tmp_path)
