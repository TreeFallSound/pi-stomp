"""v3-specific fixtures — delegates stack construction to integration/conftest."""
import time as _time
from collections.abc import Generator

import pytest

from modalapi.wifi import SavedConnection, ScannedNetwork
from tests.integration.conftest import _v3_stack
from tests.types import SystemFixture


@pytest.fixture
def v3_system(fake_lcd, tmp_path) -> Generator[SystemFixture, None, None]:
    yield from _v3_stack(fake_lcd, tmp_path)


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
