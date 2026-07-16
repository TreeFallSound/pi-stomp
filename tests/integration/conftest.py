"""
Parametrized stack fixtures for cross-version integration tests.

  modhandler_system  — Modhandler-based hardware (v2, v3).
"""

import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from tests.conftest import FakeWebSocketBridge
from tests.types import CapturedLcd, SystemFixture
import common.token as Token

PROJECT_ROOT = Path(__file__).parent.parent.parent

with patch("pistomp.settings.Settings.load_settings"), patch("pistomp.settings.Settings.set_setting"):
    from modalapi.modhandler import Modhandler
    from pistomp.hardware import Hardware
    from pistomp.pistompcore import Pistompcore
    from pistomp.pistomptre import Pistomptre


# ---------------------------------------------------------------------------
# Shared stack builder
# ---------------------------------------------------------------------------


def _build_stack(
    hw_class: type[Hardware],
    fake_lcd: CapturedLcd,
    cfg_path: Path,
    tmp_path: Path,
) -> Generator[SystemFixture, None, None]:
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
        patch("pistomp.httpclient.get") as mock_get,
        patch("pistomp.httpclient.post") as mock_post,
        patch("pistomp.settings.Settings") as mock_settings_cls,
        patch("modalapi.pedalboard.Pedalboard.hydrate"),
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
        handler.recovery_available = False  # no pistomp-recovery in test env
        assert isinstance(handler.settings, MagicMock)
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

        # Wire the FakeLcd's flush callback to the pstack so the snapshot
        # fixture can flush deferred LCD pushes before capturing a frame.
        pstack = handler._lcd.pstack if handler._lcd is not None else None
        if pstack is not None:
            fake_lcd.flush_callback = pstack.poll_updates

        yield SystemFixture(handler, hw, fake_lcd, mock_get, mock_post, fake_bridge)


# ---------------------------------------------------------------------------
# Per-version stack builders
# ---------------------------------------------------------------------------


def _v2_stack(fake_lcd, tmp_path) -> Generator[SystemFixture, None, None]:
    cfg_path = PROJECT_ROOT / "setup" / "config_templates" / "default_config_pistompcore.yml"
    yield from _build_stack(Pistompcore, fake_lcd, cfg_path, tmp_path)


def _v3_stack(fake_lcd, tmp_path) -> Generator[SystemFixture, None, None]:
    cfg_path = PROJECT_ROOT / "setup" / "config_templates" / "default_config_pistomptre.yml"
    yield from _build_stack(Pistomptre, fake_lcd, cfg_path, tmp_path)


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
