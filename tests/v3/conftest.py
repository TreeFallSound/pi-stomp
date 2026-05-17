"""v3-specific fixtures — delegates stack construction to integration/conftest."""

import json
import time as _time
from collections.abc import Generator
from typing import cast
from unittest.mock import MagicMock

import pytest
import yaml

import common.token as Token
from modalapi.wifi import SavedConnection, ScannedNetwork
from tests.conftest import FakeWebSocketBridge
from tests.integration.conftest import _v3_stack
from tests.types import SystemFixture


@pytest.fixture
def v3_system(fake_lcd, tmp_path) -> Generator[SystemFixture, None, None]:
    yield from _v3_stack(fake_lcd, tmp_path)


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


@pytest.fixture
def blend_system(
    v3_system: SystemFixture, tmp_path, make_plugin, make_parameter
) -> Generator[SystemFixture, None, None]:
    """
    v3 stack with a fully prepared and activated blend mode.

    Bundle layout in tmp_path:
      blend_rig.pedalboard/
        snapshots.json   — Clean (0) and Lead (1)
        config.yml       — blend_snapshots config using encoder id=1

    Pedalboard contains a single BigMuff plugin (Tone, Level, :bypass).

    After setup:
      handler.blend_modes["Blend"]  — prepared BlendMode
      handler.active_blend_mode     — activated, encoder id=1 hijacked
      handler.ws_bridge.sent        — cleared (ready for test assertions)
    """
    handler = v3_system.handler
    hw = v3_system.hw
    lcd = v3_system.lcd
    mock_get = v3_system.mock_get
    mock_post = v3_system.mock_post

    bundle_dir = tmp_path / "blend_rig.pedalboard"
    bundle_dir.mkdir()
    (bundle_dir / "snapshots.json").write_text(json.dumps(_BLEND_SNAPSHOTS))
    (bundle_dir / "config.yml").write_text(yaml.dump(_BLEND_CONFIG))

    def get_side_effect(url, **kwargs):
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
            # Index 2 is the blend snapshot created by sync_blend_snapshots
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

    # Clear WS captures from initial sync so tests start with a clean slate
    cast(FakeWebSocketBridge, handler.ws_bridge).sent.clear()

    yield SystemFixture(handler, hw, lcd, mock_get, mock_post, v3_system.ws_bridge)


# ---------------------------------------------------------------------------
# WiFi test helpers
# ---------------------------------------------------------------------------

def make_scanned(ssid: str, signal: int = 60, security: str = "WPA2",
                 in_use: bool = False) -> ScannedNetwork:
    return ScannedNetwork(ssid=ssid, signal=signal, security=security, in_use=in_use)


def make_saved(ssid: str, name: str | None = None,
               timestamp: int | None = None) -> SavedConnection:
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
